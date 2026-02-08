"""
Groq-Powered Email Triage Assistant
Streamlit Dashboard

This is the main entry point for the web interface.
Run with: streamlit run app.py
"""

import streamlit as st
import time
import os
# Import backend functions
try:
    from backend import process_emails
except ImportError:
    # Fallback if backend not ready (though it should be)
    def process_emails(dry_run=False):
        return {"status": "error", "message": "Backend module missing"}

from utils import load_config, save_config, set_account_password

# Page configuration
st.set_page_config(
    page_title="Email Triage Assistant",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load config
config = load_config()

st.title("📧 Email Triage Assistant")

# Sidebar for status
with st.sidebar:
    st.header("System Status")
    
    # Provider Info
    settings = config.get("settings", {})
    provider = settings.get("provider", "groq")
    st.info(f"🧠 **AI Brain:** {provider.upper()}")
    
    # Model Info
    provider_config = config.get("providers", {}).get(provider, {})
    model = provider_config.get("model", "unknown")
    st.caption(f"Model: {model}")
    
    # Active Accounts
    accounts = config.get("accounts", [])
    enabled_accounts = [a for a in accounts if a.get("enabled", True)]
    st.metric("Active Accounts", len(enabled_accounts))
    
    st.divider()
    
    # Quick Actions
    if st.button("🔄 Refresh Config"):
        st.cache_data.clear()
        st.rerun()

# Create tabs
tab_dashboard, tab_accounts, tab_settings = st.tabs([
    "📊 Dashboard & Logs",
    "📬 Accounts Manager", 
    "⚙️ Intelligence & Rules"
])

# --- DASHBOARD TAB ---
with tab_dashboard:
    st.header("Mission Control")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Run button with status
        if st.button("▶️ Run Triage Now", type="primary", use_container_width=True):
            status_container = st.status("🚀 Starting Triage Engine...", expanded=True)
            
            try:
                # 1. Connect
                status_container.write("🔄 Connecting to email servers...")
                time.sleep(1) # Visual feedback
                
                # 2. Process
                status_container.write(f"🧠 Analyzing emails with {provider.upper()}...")
                results = process_emails(dry_run=config.get("settings", {}).get("dry_run", False))
                
                # 3. Report
                if results.get("status") == "error":
                    status_container.update(label="❌ Triage Failed", state="error", expanded=True)
                    st.error(results.get("message"))
                else:
                    status_container.update(label="✅ Triage Complete", state="complete", expanded=False)
                    
                    # Success Notification
                    processed_count = results.get("processed", 0)
                    error_count = results.get("errors", 0)
                    skipped_count = results.get("skipped", 0)
                    
                    if processed_count > 0:
                        st.success(f"Successfully processed {processed_count} emails!")
                    elif skipped_count > 0:
                         st.warning(f"Processed 0 emails, but skipped {skipped_count} (check logs).")
                    else:
                        st.info("No new emails found to process.")
                    
                    # Show Metrics
                    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                    m_col1.metric("Processed", processed_count)
                    m_col2.metric("Skipped", skipped_count)
                    m_col3.metric("Errors", error_count)
                    m_col4.metric("Mode", "Dry Run" if settings.get("dry_run") else "Live Action")
                    
                    # Show Details Table
                    details = results.get("details", [])
                    if details:
                        st.subheader("Action Log")
                        st.dataframe(details, use_container_width=True)
                        
            except Exception as e:
                status_container.update(label="❌ Critical Error", state="error")
                st.error(f"An unexpected error occurred: {str(e)}")

    with col2:
        st.subheader("Daily Briefing")
        
        # Display the content of daily_briefing.md
        briefing_file = "daily_briefing.md"
        if os.path.exists(briefing_file):
            try:
                with open(briefing_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    st.markdown(content)
            except Exception as e:
                st.error(f"Could not read briefing: {e}")
        else:
            st.info("Briefings will appear here after triage runs.")
            
        if st.button("🔄 Refresh Briefing"):
            st.rerun()

# --- COMPLETED ---

# --- ACCOUNTS TAB ---
with tab_accounts:
    st.header("Email Accounts")
    
    # List existing accounts
    if not accounts:
        st.warning("No accounts configured! Add one below to get started.")
    
    # Edit/Delete existing
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
    
    # Add new account form
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
                    "provider": "imap" # default
                }
                
                # Add to config
                if "accounts" not in config:
                    config["accounts"] = []
                config["accounts"].append(new_acc)
                save_config(config)
                
                # Save password to .env (using utils function)
                set_account_password(acc_id, password)
                
                st.success(f"Account '{acc_id}' added successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Please fill in all fields.")

# --- SETTINGS TAB ---
with tab_settings:
    st.header("Intelligence & Rules")
    
    st.subheader("Brain Configuration")
    
    # Provider Selection
    curr_provider = settings.get("provider", "groq")
    new_provider = st.selectbox(
        "AI Provider", 
        ["groq", "deepseek"], 
        index=0 if curr_provider == "groq" else 1
    )
    
    if new_provider != curr_provider:
        # Update provider in config
        config.setdefault("settings", {})["provider"] = new_provider
        save_config(config)
        st.rerun()
        
    # Provider specific settings link
    st.caption(f"Configured to use **{new_provider.upper()}** models.")

    st.divider()

    st.subheader("Triage Rules")
    
    # System Prompt Editor
    st.write(" **Assistant Instructions (System Prompt)**")
    new_prompt = st.text_area(
        "Instructions", 
        value=config.get("system_prompt", ""),
        height=200
    )
    
    if st.button("Save Intelligence Settings"):
        config["system_prompt"] = new_prompt
        save_config(config)
        st.success("Settings updated!")
