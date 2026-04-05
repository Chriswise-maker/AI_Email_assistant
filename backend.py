"""
Groq-Powered Email Triage Assistant
Backend Engine

This module handles:
- Multi-account IMAP connections (persistent)
- Email fetching and cleaning
- LLM API integration (via llm_providers.py)
- Rule execution (flag, move, mark read)
- Daily briefing generation
"""

import sys
import json
import time
import traceback
import datetime
from pathlib import Path
from typing import Optional, List
from bs4 import BeautifulSoup
from imap_tools import MailBox, AND
from imap_tools import MailMessage

from utils import load_config, get_account_password, get_env_value, PROJECT_ROOT
from llm_providers import get_provider

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


def process_emails(dry_run: bool = False) -> dict:
    """
    Main entry point for email processing.
    
    Iterates through all enabled accounts, fetches unseen emails,
    analyzes them with configured LLM, applies configured rules,
    and updates the daily briefing.
    """
    config = load_config()
    accounts = config.get("accounts", [])
    settings = config.get("settings", {})
    
    fetch_limit = settings.get("fetch_limit", 50)
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

    stats = {"processed": 0, "errors": 0, "skipped": 0, "details": []}
    all_summaries = [] # List of {account, subject, summary, category, priority}

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
                # Fetch ALL UNSEEN messages from INBOX
                # mark_seen=False so failed emails stay unread for next run
                emails = list(mailbox.fetch(AND(seen=False), mark_seen=False))
                
                if fetch_limit:
                    emails = emails[:fetch_limit]

                print(f"  Found {len(emails)} unseen emails in INBOX.")

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
                            
                            # Collect for briefing
                            all_summaries.append({
                                "account": account_id,
                                "sender": email.from_,
                                "subject": email.subject,
                                "category": category,
                                "priority": priority, # Int guaranteed
                                "summary": analysis.get("summary", "")
                            })
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

    # 4. Generate Daily Briefing
    if all_summaries:
        append_to_briefing(all_summaries)

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


def append_to_briefing(summaries: List[dict]) -> None:
    """
    Prepend processed email summaries to daily_briefing.md (newest first)
    Group by Category first, then sort by Priority (desc).
    """
    briefing_path = PROJECT_ROOT / "daily_briefing.md"
    
    # Sort: Category -> Priority (desc)
    # Ensure priority is int for robust sorting
    summaries.sort(key=lambda x: (x.get('category', 'Other'), -int(x.get('priority', 1))))
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    markdown = f"\n##  Briefing Run: {timestamp}\n"
    markdown += f"Processed {len(summaries)} emails.\n\n"
    
    current_category = None
    
    for item in summaries:
        category = item.get('category', 'Other')
        if category != current_category:
            current_category = category
            markdown += f"### {current_category}\n"
        
        p = int(item.get('priority', 1))
        
        # Priority Icons
        if p >= 5:
            icon = "🔴" # Urgent
        elif p >= 4:
            icon = "🟠" # High
        elif p == 3:
            icon = "🟡" # Medium
        else:
            icon = "⚪" # Low
        
        subject = item.get('subject', 'No Subject')
        sender = item.get('sender', 'Unknown')
        summary = item.get('summary', 'No summary provided')
        
        account = item.get('account', '')
        acct_tag = f" [{account}]" if account else ""
        markdown += f"- {icon} **{subject}** (from {sender}){acct_tag}\n"
        markdown += f"  > {summary}\n"
    
    markdown += "\n---\n"
    
    try:
        # Prepend by reading existing content first
        existing_content = ""
        if briefing_path.exists():
            with open(briefing_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
        
        # Write new content followed by old content
        with open(briefing_path, "w", encoding="utf-8") as f:
            f.write(markdown + existing_content)
    except Exception as e:
        print(f"Error writing to daily_briefing.md: {e}")

