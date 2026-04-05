"""
Groq-Powered Email Triage Assistant
Streamlit Dashboard

This is the main entry point for the web interface.
Run with: streamlit run app.py
"""

import streamlit as st
import time
import os
import re
import html
from collections import defaultdict

# Import backend functions
try:
    from backend import process_emails, CANONICAL_CATEGORIES
except ImportError:
    def process_emails(dry_run=False):
        return {"status": "error", "message": "Backend module missing"}
    CANONICAL_CATEGORIES = ["Security", "Bills & Invoices", "Orders & Shipping",
                            "Newsletters", "Personal", "Notifications", "Spam", "Other"]

import json
from utils import load_config, save_config, set_account_password, set_env_variable, get_env_value, PROJECT_ROOT

# --- Page Configuration ---
st.set_page_config(
    page_title="Email Triage Assistant",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Custom CSS ---
st.markdown("""
<style>
    /* Overall darker theme feel */
    .block-container { padding-top: 1.5rem; }
    
    /* Priority Badges */
    .priority-critical {
        background: linear-gradient(135deg, #ff4b4b 0%, #c62828 100%);
        color: white; padding: 3px 10px; border-radius: 12px;
        font-size: 0.75rem; font-weight: 600; display: inline-block;
    }
    .priority-high {
        background: linear-gradient(135deg, #ff9800 0%, #e65100 100%);
        color: white; padding: 3px 10px; border-radius: 12px;
        font-size: 0.75rem; font-weight: 600; display: inline-block;
    }
    .priority-medium {
        background: linear-gradient(135deg, #fdd835 0%, #f9a825 100%);
        color: #333; padding: 3px 10px; border-radius: 12px;
        font-size: 0.75rem; font-weight: 600; display: inline-block;
    }
    .priority-low {
        background: #e0e0e0; color: #555;
        padding: 3px 10px; border-radius: 12px;
        font-size: 0.75rem; font-weight: 600; display: inline-block;
    }
    
    /* Email card style */
    .email-card {
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
        background: rgba(255,255,255,0.03);
        transition: background 0.2s;
    }
    .email-card:hover {
        background: rgba(255,255,255,0.07);
    }
    .email-subject { font-weight: 600; font-size: 0.95rem; }
    .email-sender { color: #888; font-size: 0.82rem; }
    .email-summary { font-size: 0.88rem; margin-top: 4px; line-height: 1.4; }
    .email-account-tag {
        background: rgba(100,100,255,0.15); color: #8888ff;
        padding: 1px 8px; border-radius: 8px; font-size: 0.72rem;
        font-weight: 500; display: inline-block; margin-left: 6px;
    }
    
    /* Category tab icons */
    .cat-count {
        background: rgba(128,128,128,0.2); padding: 1px 7px;
        border-radius: 10px; font-size: 0.75rem; margin-left: 4px;
    }
    
    /* Section headers */
    .section-header {
        font-size: 1.1rem; font-weight: 600;
        margin: 0.5rem 0 0.8rem 0; padding-bottom: 0.4rem;
        border-bottom: 2px solid rgba(128,128,128,0.15);
    }
    
    /* Compact metrics */
    [data-testid="stMetric"] { padding: 8px 0; }
    
    /* Alert banner */
    .alert-banner {
        background: linear-gradient(135deg, rgba(255,75,75,0.12) 0%, rgba(255,152,0,0.08) 100%);
        border-left: 4px solid #ff4b4b;
        border-radius: 0 8px 8px 0;
        padding: 10px 16px;
        margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# --- Load Config ---
config = load_config()
settings = config.get("settings", {})
accounts = config.get("accounts", [])
provider = settings.get("provider", "groq")

# --- Briefing Parser ---
def parse_briefing_file(filepath=None):
    """Parse the briefing markdown into structured data.
    Returns list of dicts: {subject, sender, summary, category, priority_icon, priority_level, account, run_timestamp}
    Only parses the LATEST briefing run.
    """
    if filepath is None:
        filepath = PROJECT_ROOT / "daily_briefing.md"
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []
    
    if not content.strip():
        return []
    
    entries = []
    current_category = "Other"
    
    # Find the first briefing run section (latest, since newest is prepended)
    # Split on the horizontal rule to isolate the first run
    runs = content.split("\n---\n")
    if not runs:
        return []
    
    latest_run = runs[0]
    
    # Extract timestamp
    ts_match = re.search(r"Briefing Run:\s*(.+)", latest_run)
    run_timestamp = ts_match.group(1).strip() if ts_match else ""
    
    for line in latest_run.split("\n"):
        line = line.strip()
        
        # Category header
        if line.startswith("### "):
            current_category = line[4:].strip()
            continue
        
        # Email entry: - 🔴 **Subject** (from sender) [Account]
        entry_match = re.match(
            r"^- (🔴|🟠|🟡|⚪)\s+\*\*(.+?)\*\*\s+\(from\s+(.+?)\)\s*(\[.+?\])?\s*$",
            line
        )
        if entry_match:
            icon = entry_match.group(1)
            subject = entry_match.group(2)
            sender = entry_match.group(3)
            account = entry_match.group(4) or ""
            account = account.strip("[]") if account else ""
            
            # Map icon to priority level for sorting
            priority_map = {"🔴": 5, "🟠": 4, "🟡": 3, "⚪": 1}
            priority_level = priority_map.get(icon, 1)
            
            entries.append({
                "subject": subject,
                "sender": sender,
                "summary": "",  # Will be filled by next line
                "category": current_category,
                "priority_icon": icon,
                "priority_level": priority_level,
                "account": account,
                "run_timestamp": run_timestamp,
            })
            continue
        
        # Summary line (blockquote)
        if line.startswith("> ") and entries:
            entries[-1]["summary"] = line[2:].strip()
    
    return entries

def render_email_card(entry):
    """Render a single email entry as a styled card."""
    icon = entry["priority_icon"]
    subject = html.escape(entry["subject"])
    sender = html.escape(entry["sender"])
    summary = html.escape(entry["summary"])
    account = html.escape(entry["account"])

    acct_html = f'<span class="email-account-tag">{account}</span>' if account else ""
    
    # Priority badge
    plevel = entry["priority_level"]
    if plevel >= 5:
        badge = '<span class="priority-critical">URGENT</span>'
    elif plevel >= 4:
        badge = '<span class="priority-high">HIGH</span>'
    elif plevel >= 3:
        badge = '<span class="priority-medium">MEDIUM</span>'
    else:
        badge = '<span class="priority-low">LOW</span>'
    
    st.markdown(f"""
    <div class="email-card">
        <div>{icon} {badge} {acct_html}</div>
        <div class="email-subject">{subject}</div>
        <div class="email-sender">from {sender}</div>
        <div class="email-summary">{summary}</div>
    </div>
    """, unsafe_allow_html=True)

# --- HEADER ---
st.title("📧 Email Triage Assistant")

# --- Sidebar (system status, compact) ---
with st.sidebar:
    st.header("⚙️ System")
    provider_config = config.get("providers", {}).get(provider, {})
    model = provider_config.get("model", "unknown")
    st.caption(f"🧠 {provider.upper()} · {model}")
    enabled_accounts = [a for a in accounts if a.get("enabled", True)]
    st.caption(f"📬 {len(enabled_accounts)} active account{'s' if len(enabled_accounts) != 1 else ''}")
    st.divider()
    if st.button("🔄 Refresh Config"):
        st.cache_data.clear()
        st.rerun()

# --- Create Tabs ---
tab_dashboard, tab_accounts, tab_settings, tab_debug = st.tabs([
    "📊 Dashboard",
    "📬 Accounts",
    "⚙️ Settings",
    "🐛 Debug",
])

# ============================================================
# DASHBOARD TAB
# ============================================================
with tab_dashboard:
    
    # --- Row 1: Triage Controls (compact) ---
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])
    
    with ctrl_col1:
        run_clicked = st.button("▶️ Run Triage Now", type="primary", use_container_width=True)
    with ctrl_col2:
        mode_label = "🧪 Dry Run" if settings.get("dry_run") else "⚡ Live"
        st.markdown(f"**Mode:** {mode_label}")
    with ctrl_col3:
        if st.button("🔄 Refresh Briefing"):
            st.rerun()
    
    # Process emails if button clicked
    if run_clicked:
        status_container = st.status("🚀 Starting Triage Engine...", expanded=True)
        try:
            status_container.write("🔄 Connecting to email servers...")
            time.sleep(0.5)
            status_container.write(f"🧠 Analyzing emails with {provider.upper()}...")
            results = process_emails(dry_run=settings.get("dry_run", False))
            
            if results.get("status") == "error":
                status_container.update(label="❌ Triage Failed", state="error", expanded=True)
                st.error(results.get("message"))
            else:
                status_container.update(label="✅ Triage Complete", state="complete", expanded=False)
                processed_count = results.get("processed", 0)
                error_count = results.get("errors", 0)
                skipped_count = results.get("skipped", 0)
                
                if processed_count > 0:
                    st.success(f"Successfully processed {processed_count} emails!")
                elif skipped_count > 0:
                    st.warning(f"Processed 0 emails, but skipped {skipped_count}.")
                else:
                    st.info("No new emails found to process.")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Processed", processed_count)
                m2.metric("Skipped", skipped_count)
                m3.metric("Errors", error_count)
                
                details = results.get("details", [])
                if details:
                    with st.expander("📋 Action Log", expanded=False):
                        st.dataframe(details, use_container_width=True)
                
                # Force rerun to show updated briefing
                time.sleep(1)
                st.rerun()
        except Exception as e:
            status_container.update(label="❌ Critical Error", state="error")
            st.error(f"An unexpected error occurred: {str(e)}")
    
    st.divider()
    
    # --- Parse briefing data ---
    entries = parse_briefing_file()
    
    if not entries:
        st.info("📭 No briefing data yet. Run triage to populate your daily briefing.")
    else:
        # Show run timestamp
        if entries[0].get("run_timestamp"):
            st.caption(f"📅 Latest briefing: {entries[0]['run_timestamp']}")
        
        # --- Row 2: Priority Alerts (urgent + high only) ---
        urgent_entries = [e for e in entries if e["priority_level"] >= 4]
        
        if urgent_entries:
            st.markdown('<div class="section-header">🚨 Priority Alerts</div>', unsafe_allow_html=True)
            for entry in sorted(urgent_entries, key=lambda x: -x["priority_level"]):
                render_email_card(entry)
            st.divider()
        
        # --- Row 3: Full Briefing by Category (tabs) ---
        st.markdown('<div class="section-header">📂 All Emails by Category</div>', unsafe_allow_html=True)
        
        # Group entries by category
        by_category = defaultdict(list)
        for entry in entries:
            by_category[entry["category"]].append(entry)
        
        # Build tab labels with counts — only show categories that have entries
        # Use canonical order, then append any non-canonical categories
        ordered_cats = []
        for cat in CANONICAL_CATEGORIES:
            if cat in by_category:
                ordered_cats.append(cat)
        for cat in by_category:
            if cat not in ordered_cats:
                ordered_cats.append(cat)
        
        # Category icons
        cat_icons = {
            "Security": "🔒",
            "Bills & Invoices": "💰",
            "Orders & Shipping": "📦",
            "Newsletters": "📰",
            "Personal": "👤",
            "Notifications": "🔔",
            "Spam": "🗑️",
            "Other": "📋",
        }
        
        tab_labels = [f"{cat_icons.get(cat, '📁')} {cat} ({len(by_category[cat])})" for cat in ordered_cats]
        
        if tab_labels:
            cat_tabs = st.tabs(tab_labels)
            
            for i, cat in enumerate(ordered_cats):
                with cat_tabs[i]:
                    cat_entries = sorted(by_category[cat], key=lambda x: -x["priority_level"])
                    for entry in cat_entries:
                        render_email_card(entry)
        else:
            st.info("No categorized emails to display.")


# ============================================================
# ACCOUNTS TAB
# ============================================================
with tab_accounts:
    st.header("Email Accounts")
    
    if not accounts:
        st.warning("No accounts configured! Add one below to get started.")
    
    for i, account in enumerate(accounts):
        with st.expander(f"📧 {account.get('id')} ({account.get('email')})"):
            c1, c2 = st.columns(2)
            c1.write(f"**Server:** {account.get('server')}")
            c2.write(f"**Status:** {'✅ Enabled' if account.get('enabled') else '❌ Disabled'}")
            
            if st.button("Remove Account", key=f"del_{i}"):
                accounts.pop(i)
                save_config(config)
                st.rerun()

    st.divider()
    
    st.subheader("Add New Account")
    with st.form("add_account_form"):
        c1, c2 = st.columns(2)
        acc_id = c1.text_input("Nickname (e.g. 'Work')")
        email = c2.text_input("Email Address")
        server = st.text_input("IMAP Server (e.g. imap.gmail.com)")
        password = st.text_input("App Password", type="password", help="Use an App Password!")
        
        if st.form_submit_button("Save Account"):
            if acc_id and email and server and password:
                new_acc = {
                    "id": acc_id,
                    "email": email,
                    "server": server,
                    "enabled": True,
                    "provider": "imap"
                }
                if "accounts" not in config:
                    config["accounts"] = []
                config["accounts"].append(new_acc)
                save_config(config)
                set_account_password(acc_id, password)
                st.success(f"Account '{acc_id}' added successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Please fill in all fields.")


# ============================================================
# SETTINGS TAB
# ============================================================
with tab_settings:
    st.header("Intelligence & Rules")
    
    st.subheader("Brain Configuration")
    
    curr_provider = settings.get("provider", "groq")
    PROVIDERS = ["groq", "deepseek", "gemini", "claude"]
    
    try:
        current_index = PROVIDERS.index(curr_provider)
    except ValueError:
        current_index = 0
        
    s_col1, s_col2 = st.columns([1, 2])
    
    with s_col1:
        new_provider = st.radio("Select AI Brain", PROVIDERS, index=current_index, format_func=lambda x: x.upper())
        
    with s_col2:
        st.info(f"Configuring **{new_provider.upper()}**")
        
        if "providers" not in config:
            config["providers"] = {}
            
        p_config = config.get("providers", {}).get(new_provider, {})
        
        curr_model = p_config.get("model", "")
        new_model = st.text_input("Model ID", value=curr_model, help="e.g. gemini-3-flash-preview")
        
        env_var_name = p_config.get("api_key_env", f"{new_provider.upper()}_API_KEY")
        is_set = get_env_value(env_var_name) is not None
        placeholder = "********" if is_set else ""
        
        new_key = st.text_input(
            f"API Key ({env_var_name})", 
            type="password", 
            placeholder=placeholder,
            help="Leave empty to keep existing key"
        )
        
        new_thinking = None
        if new_provider in ["gemini", "claude"]:
            curr_thinking = p_config.get("thinking_level", "low" if new_provider == "gemini" else "medium")
            new_thinking = st.select_slider(
                "Thinking Level", 
                options=["low", "medium", "high"], 
                value=curr_thinking,
                help="Controls reasoning depth (Claude 'effort' / Gemini 'thinking_level')"
            )
            
        if st.button("💾 Save AI Settings"):
            config.setdefault("settings", {})["provider"] = new_provider
            
            if new_provider not in config["providers"]:
                config["providers"][new_provider] = {}
                
            config["providers"][new_provider]["model"] = new_model
            config["providers"][new_provider]["api_key_env"] = env_var_name
            
            if new_thinking:
                config["providers"][new_provider]["thinking_level"] = new_thinking
            
            save_config(config)
            
            if new_key:
                set_env_variable(env_var_name, new_key)
                st.success(f"API Key saved to .env as {env_var_name}")
            
            st.success("Configuration updated!")
            time.sleep(1)
            st.rerun()

    st.divider()

    st.subheader("Triage Rules")
    
    st.write("**Assistant Instructions (System Prompt)**")
    new_prompt = st.text_area(
        "Instructions", 
        value=config.get("system_prompt", ""),
        height=200
    )
    
    if st.button("Save Intelligence Settings"):
        config["system_prompt"] = new_prompt
        save_config(config)
        st.success("Settings updated!")


# ============================================================
# DEBUG TAB
# ============================================================
with tab_debug:
    st.header("Debug Log")

    debug_log_path = PROJECT_ROOT / "debug_logs.json"

    col_refresh, col_clear = st.columns([1, 1])
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun()
    with col_clear:
        if st.button("🗑️ Clear Log", type="secondary"):
            if debug_log_path.exists():
                debug_log_path.unlink()
            st.success("Log cleared.")
            st.rerun()

    if not debug_log_path.exists():
        st.info("No debug log yet. Run triage to generate entries.")
    else:
        try:
            with open(debug_log_path, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception as e:
            st.error(f"Failed to read debug_logs.json: {e}")
            logs = []

        if not logs:
            st.info("Log file is empty.")
        else:
            st.caption(f"{len(logs)} entries (newest first)")

            # Filter controls
            fc1, fc2 = st.columns(2)
            level_filter = fc1.multiselect(
                "Level", options=["INFO", "WARN", "ERROR"], default=["INFO", "WARN", "ERROR"]
            )
            account_options = sorted({e.get("account", "") for e in logs if e.get("account")})
            account_filter = fc2.multiselect("Account", options=account_options, default=account_options)

            filtered = [
                e for e in logs
                if e.get("level") in level_filter and e.get("account", "") in account_filter
            ]

            st.caption(f"Showing {len(filtered)} of {len(logs)} entries")

            # Level badge colours
            level_colours = {"INFO": "🟢", "WARN": "🟡", "ERROR": "🔴"}

            for entry in filtered:
                level = entry.get("level", "INFO")
                icon = level_colours.get(level, "⚪")
                ts = entry.get("timestamp", "")[:19].replace("T", " ")
                subject = entry.get("subject", "(no subject)")
                account = entry.get("account", "")
                category = entry.get("category", "")
                action = entry.get("action", "")
                priority = entry.get("priority")
                dry = " [DRY RUN]" if entry.get("dry_run") else ""

                with st.expander(f"{icon} {ts}  ·  {subject[:60]}{dry}"):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Account:** {account}")
                    c2.markdown(f"**Category:** {category}")
                    c3.markdown(f"**Priority:** {priority if priority is not None else '—'}")
                    st.markdown(f"**Action:** `{action}`")
                    st.markdown(f"**Sender:** {entry.get('sender', '')}")
                    if entry.get("error"):
                        st.error(f"**Error:** {entry['error']}")
