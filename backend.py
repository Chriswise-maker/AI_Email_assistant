"""
Groq-Powered Email Triage Assistant
Backend Engine

This module handles:
- Multi-account IMAP connections (persistent)
- Email fetching and cleaning
- LLM API integration (via llm_providers.py)
- Rule execution (flag, move, mark read)
- Persisting results to SQLite (via database.py)
"""

import sys
import json
import time
import traceback
import datetime
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup
from imap_tools import MailBox, AND
from imap_tools import MailMessage

from utils import load_config, get_account_password, get_env_value, PROJECT_ROOT
from llm_providers import get_provider
from database import create_run, finish_run, save_email

# Canonical categories — must match config.yaml and system prompt
CANONICAL_CATEGORIES = [
    "Security",
    "Bills & Invoices",
    "Orders & Shipping",
    "Newsletters",
    "Personal",
    "Notifications",
    "Spam",
    "Other",
]

# Fuzzy mapping for common LLM variations
_CATEGORY_ALIASES = {
    "bill": "Bills & Invoices",
    "bills": "Bills & Invoices",
    "invoice": "Bills & Invoices",
    "bill/invoice": "Bills & Invoices",
    "receipt": "Bills & Invoices",
    "order confirmation": "Orders & Shipping",
    "order": "Orders & Shipping",
    "shipping": "Orders & Shipping",
    "shipping update": "Orders & Shipping",
    "delivery": "Orders & Shipping",
    "newsletter": "Newsletters",
    "security alert": "Security",
    "security update": "Security",
    "security warning": "Security",
    "notification": "Notifications",
    "verification": "Notifications",
    "welcome email": "Notifications",
    "welcome/confirmation email": "Notifications",
    "confirmation email": "Notifications",
    "transactional": "Orders & Shipping",
    "administrative": "Notifications",
    "utility": "Bills & Invoices",
    "urgent": "Security",
    "important": "Personal",
    "spam": "Spam",
    "personal": "Personal",
    "other": "Other",
}

def normalize_category(raw_category: str) -> str:
    """Map LLM-returned category to a canonical one."""
    if not raw_category:
        return "Other"
    # Exact match first
    for canon in CANONICAL_CATEGORIES:
        if raw_category.strip().lower() == canon.lower():
            return canon
    # Alias lookup
    alias = _CATEGORY_ALIASES.get(raw_category.strip().lower())
    if alias:
        return alias
    # Substring match as last resort
    lower = raw_category.strip().lower()
    for canon in CANONICAL_CATEGORIES:
        if canon.lower() in lower or lower in canon.lower():
            return canon
    return "Other"

DEBUG_LOG_PATH = PROJECT_ROOT / "debug_logs.json"
_MAX_DEBUG_ENTRIES = 500  # Cap so the file doesn't grow unbounded


def write_debug_log(entry: dict) -> None:
    """Append a structured entry to debug_logs.json (newest first, capped at _MAX_DEBUG_ENTRIES)."""
    try:
        logs = []
        if DEBUG_LOG_PATH.exists():
            with open(DEBUG_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.insert(0, entry)
        logs = logs[:_MAX_DEBUG_ENTRIES]
        with open(DEBUG_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error writing debug log: {e}")


def _email_sort_key(msg) -> datetime.datetime:
    """Timezone-safe sort key for IMAP messages.

    imap_tools returns tz-aware datetimes for emails whose Date header carries a
    timezone, but naive datetimes for headers that lack one or are unparseable
    (1900-01-01). Sorting a mixed list raises TypeError, so coerce everything to
    an aware UTC datetime (treating naive values as UTC).
    """
    d = getattr(msg, "date", None)
    if d is None:
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    if d.tzinfo is None:
        return d.replace(tzinfo=datetime.timezone.utc)
    return d


def process_emails(dry_run: bool = False) -> dict:
    """
    Main entry point for email processing.

    Iterates through all enabled accounts, fetches unseen emails,
    analyzes them with configured LLM, applies configured rules,
    and persists results to the SQLite database.
    """
    config = load_config()
    accounts = config.get("accounts", [])
    settings = config.get("settings", {})
    
    fetch_limit = settings.get("fetch_limit", 50)
    max_age_days = settings.get("max_email_age_days", 30)
    provider_name = settings.get("provider", "groq")
    
    # Provider setup
    provider_config = config.get("providers", {}).get(provider_name, {})
    model_name = provider_config.get("model", "llama3-70b-8192")
    api_key_env = provider_config.get("api_key_env", "GROQ_API_KEY")
    
    api_key = get_env_value(api_key_env)
    
    if not api_key:
        return {
            "status": "error", 
            "message": f"Missing API key for provider '{provider_name}' (expected env var: {api_key_env})"
        }

    try:
        llm_provider = get_provider(provider_name, api_key, config)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    # Create a triage run in the database
    run_id = create_run(provider=provider_name, model=model_name)

    stats = {"processed": 0, "errors": 0, "skipped": 0, "details": []}

    for account in accounts:
        if not account.get("enabled", True):
            continue
            
        account_id = account.get("id")
        email_addr = account.get("email")
        server = account.get("server")
        password = get_account_password(account_id)
        
        if not password:
            print(f"Skipping {account_id}: No password found")
            stats["details"].append({"account": account_id, "error": "No password found"})
            continue

        print(f"Processing account: {account_id} ({email_addr})")
        
        try:
            # Persistent connection per account
            with MailBox(server).login(email_addr, password, initial_folder='INBOX') as mailbox:
                # Fetch UNSEEN messages from INBOX, filtered by age
                # mark_seen=False so failed emails stay unread for next run
                date_cutoff = datetime.date.today() - datetime.timedelta(days=max_age_days)
                emails = list(mailbox.fetch(
                    AND(seen=False, date_gte=date_cutoff),
                    mark_seen=False,
                ))

                # Sort newest-first so the fetch_limit keeps recent emails
                # (IMAP returns oldest-first by default)
                emails.sort(key=_email_sort_key, reverse=True)

                if fetch_limit:
                    emails = emails[:fetch_limit]

                total_fetched = len(emails)
                print(f"  Found {total_fetched} unseen emails in INBOX (since {date_cutoff}).")
                write_debug_log({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "level": "INFO",
                    "event": "imap_fetch",
                    "account": account_id,
                    "emails_found": total_fetched,
                    "date_cutoff": str(date_cutoff),
                    "fetch_limit": fetch_limit,
                    "oldest_email": emails[-1].date.isoformat() if emails and emails[-1].date else None,
                    "newest_email": emails[0].date.isoformat() if emails and emails[0].date else None,
                })

                max_body_chars = settings.get("max_body_chars", 3000)

                for email in emails:
                    try:
                        # 1. Clean Body
                        cleaned_body = clean_email_body(email.html or email.text, max_chars=max_body_chars)
                        
                        # 2. Analyze (with single retry on failure)
                        analysis = analyze_email_content(
                            llm_provider,
                            cleaned_body,
                            config.get("system_prompt"),
                            model_name
                        )
                        if analysis is None:
                            print(f"  Retrying analysis for: {email.subject}")
                            time.sleep(2)
                            analysis = analyze_email_content(
                                llm_provider,
                                cleaned_body,
                                config.get("system_prompt"),
                                model_name
                            )
                        
                        if analysis:
                            category = normalize_category(analysis.get("category", "Other"))
                            action_name = config.get("rules", {}).get(category, "no_action")
                            
                            # Safely get priority as int
                            try:
                                priority = int(analysis.get("priority", 1))
                            except (ValueError, TypeError):
                                priority = 1
                            
                            # 3. Apply Rules (mark read, flag, etc)
                            # Passing mailbox and email UID to perform actions
                            apply_rules(mailbox, email.uid, action_name, dry_run)

                            # Mark as seen only after successful analysis + rule application
                            if not dry_run:
                                mailbox.flag(email.uid, '\\Seen', True)

                            stats["processed"] += 1
                            stats["details"].append({
                                "account": account_id,
                                "subject": email.subject,
                                "category": category,
                                "action": action_name
                            })
                            write_debug_log({
                                "timestamp": datetime.datetime.now().isoformat(),
                                "level": "INFO",
                                "account": account_id,
                                "subject": email.subject,
                                "sender": email.from_,
                                "category": category,
                                "priority": priority,
                                "action": action_name,
                                "dry_run": dry_run,
                            })

                            # Persist to SQLite
                            email_date_str = ""
                            if email.date:
                                email_date_str = email.date.isoformat() if hasattr(email.date, 'isoformat') else str(email.date)
                            save_email(
                                run_id=run_id,
                                uid=email.uid,
                                account=account_id,
                                sender=email.from_,
                                subject=email.subject,
                                category=category,
                                priority=priority,
                                summary=analysis.get("summary", ""),
                                action=action_name,
                                dry_run=dry_run,
                                email_date=email_date_str,
                            )

                        else:
                            print(f"  Failed to analyze: {email.subject}")
                            stats["skipped"] += 1
                            error_reason = getattr(llm_provider, "last_error", "Unknown error")
                            stats["details"].append({
                                "account": account_id,
                                "subject": email.subject,
                                "category": "Analysis Failed",
                                "action": f"Skipped — {error_reason}"
                            })
                            write_debug_log({
                                "timestamp": datetime.datetime.now().isoformat(),
                                "level": "WARN",
                                "account": account_id,
                                "subject": email.subject,
                                "sender": email.from_,
                                "category": "Analysis Failed",
                                "priority": None,
                                "action": "Skipped",
                                "error": error_reason,
                                "dry_run": dry_run,
                            })
                            
                    except Exception as e_inner:
                        print(f"  Error processing email '{email.subject}': {e_inner}")
                        stats["errors"] += 1
                        stats["details"].append({
                            "account": account_id,
                            "subject": email.subject,
                            "category": "Error",
                            "action": str(e_inner)
                        })
                        write_debug_log({
                            "timestamp": datetime.datetime.now().isoformat(),
                            "level": "ERROR",
                            "account": account_id,
                            "subject": email.subject,
                            "sender": getattr(email, "from_", ""),
                            "category": "Error",
                            "priority": None,
                            "action": str(e_inner),
                            "dry_run": dry_run,
                        })

        except Exception as e:
            print(f"Error connecting to {account_id}: {e}")
            traceback.print_exc()
            stats["errors"] += 1
            stats["details"].append({"account": account_id, "error": str(e)})

    # Finalize the run in the database
    finish_run(run_id, stats["processed"], stats["errors"], stats["skipped"])

    return stats


def clean_email_body(html_body: str, max_chars: int = 3000) -> str:
    """Strip HTML and truncate."""
    try:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())
        if not text:
            return "[Empty Email Body]"
        return text[:max_chars]
    except Exception:
        return (html_body or "[Empty Email Body]")[:max_chars]


def analyze_email_content(provider, email_content: str, system_prompt: str, model: str) -> Optional[dict]:
    """Wrapper to call the provider."""
    return provider.analyze_email(email_content, system_prompt, model)


def apply_rules(mailbox: MailBox, uid: str, action_name: str, dry_run: bool = False) -> None:
    """
    Execute action on the specific email UID using the open mailbox connection.
    """
    if dry_run:
        print(f"[DRY RUN] Would perform '{action_name}' on UID {uid}")
        return

    try:
        if action_name == "mark_read":
            mailbox.flag(uid, '\\Seen', True)
        elif action_name == "flag":
            mailbox.flag(uid, '\\Flagged', True)
        elif action_name == "delete": # Be careful with this!
            mailbox.delete(uid)
        elif action_name == "no_action":
            pass
        else:
            print(f"Unknown action: {action_name}")
            
    except Exception as e:
        print(f"Error applying rule '{action_name}' to UID {uid}: {e}")


def get_reply_draft(email_data: dict, instruction: str, config: dict) -> Optional[str]:
    """Generate a reply draft for an email using the configured LLM provider."""
    provider_name = config.get("settings", {}).get("provider", "groq")
    provider_config = config.get("providers", {}).get(provider_name, {})
    model_name = provider_config.get("model", "llama3-70b-8192")
    api_key_env = provider_config.get("api_key_env", "GROQ_API_KEY")
    api_key = get_env_value(api_key_env)

    if not api_key:
        return None

    try:
        llm = get_provider(provider_name, api_key, config)
    except ValueError:
        return None

    email_context = (
        f"From: {email_data.get('sender', '')}\n"
        f"Subject: {email_data.get('subject', '')}\n"
        f"Summary: {email_data.get('summary', '')}\n"
        f"Category: {email_data.get('category', '')}"
    )
    return llm.draft_reply(email_context, instruction, model_name)


def delete_email_from_imap(account_id: str, uid: str, config: dict) -> tuple[bool, str]:
    """Delete a specific email from IMAP by UID. Returns (success, error_message)."""
    accounts = config.get("accounts", [])
    account = next((a for a in accounts if a.get("id") == account_id), None)

    if not account:
        return False, f"Account '{account_id}' not found in config"

    email_addr = account.get("email")
    server = account.get("server")
    password = get_account_password(account_id)

    if not password:
        return False, f"No password found for account '{account_id}'"

    try:
        with MailBox(server).login(email_addr, password, initial_folder='INBOX') as mailbox:
            mailbox.delete(uid)
        return True, ""
    except Exception as e:
        return False, str(e)
