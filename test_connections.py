"""
Test script for backend connectivity.
Verifies IMAP and LLM Provider connections work before full implementation.

Run with: python test_connections.py
"""

import sys
import traceback
from time import sleep

# Ensure we can import from local directory
sys.path.append(".")

from imap_tools import MailBox, AND
from utils import load_config, get_env_value, get_account_password
from llm_providers import get_provider

def test_llm_connection():
    """Test configured LLM Provider connectivity."""
    print("\n🤖 Testing LLM Provider connection...")
    
    config = load_config()
    provider_name = config.get("settings", {}).get("provider", "groq")
    provider_config = config.get("providers", {}).get(provider_name, {})
    
    api_key_env = provider_config.get("api_key_env")
    model = provider_config.get("model")
    
    print(f"  Configuration: Provider={provider_name}, Model={model}")
    
    api_key = get_env_value(api_key_env)
    
    # Debug print (masked)
    if api_key:
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        print(f"  API Key found: {masked_key} (from {api_key_env})")
    else:
        print(f"  ❌ API Key not found in .env (expected {api_key_env})")
        return False
    
    try:
        provider = get_provider(provider_name, api_key)
        
        # Simple system prompt
        system_prompt = "You are a helpful assistant."
        
        # Simple user message
        user_message = "Say 'Hello' in exactly one word."
        
        print("  📤 Sending request...")
        response = provider.analyze_email(
            user_message, 
            system_prompt + " Return valid JSON: {'message': 'Hello'}", 
            model
        )
        
        if response:
            print(f"  ✅ {provider_name} API works!")
            print(f"     Response: {response}")
            return True
        else:
            print(f"  ❌ {provider_name} API returned None (check logs).")
            return False
            
    except Exception as e:
        print(f"  ❌ API error: {e}")
        traceback.print_exc()
        return False


def test_imap_connection():
    """Test IMAP connection for configured accounts."""
    print("\n📬 Testing IMAP connection...")
    
    config = load_config()
    accounts = config.get("accounts", [])
    
    if not accounts:
        print("  ⚠️  No accounts configured in config.yaml")
        print("     Add an account to test IMAP connectivity.")
        return None
    
    for account in accounts:
        if not account.get("enabled", True):
            print(f"  ⏭️  Skipping disabled account: {account.get('id')}")
            continue
            
        account_id = account.get("id", "unknown")
        email = account.get("email")
        server = account.get("server")
        password = get_account_password(account_id)
        
        if not password:
            print(f"  ❌ No password found for account '{account_id}'")
            continue
        
        print(f"  🔄 Connecting to {server} as {email}...")
        
        try:
            with MailBox(server).login(email, password) as mailbox:
                # Just count unseen emails to verify connection
                try:
                    msgs = list(mailbox.fetch(AND(seen=False), limit=1, mark_seen=False))
                    unseen_count = len(msgs)
                    print(f"  ✅ Connected to '{account_id}'! Found at least {unseen_count} unseen email(s).")
                    return True
                except Exception as fetch_err:
                    print(f"  ⚠️  Login successful, but fetch failed: {fetch_err}")
                    return True # Still count as connected
                
        except Exception as e:
            print(f"  ❌ IMAP connection error for '{account_id}': {e}")
            return False
    
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Backend Connectivity Tests")
    print("=" * 50)
    
    llm_ok = test_llm_connection()
    imap_result = test_imap_connection()
    
    print("\n" + "=" * 50)
    print("📊 Summary")
    print("=" * 50)
    print(f"  LLM API:   {'✅ OK' if llm_ok else '❌ FAILED'}")
    
    if imap_result is None:
        print("  IMAP:      ⚠️  Not configured")
    elif imap_result:
        print("  IMAP:      ✅ OK")
    else:
        print("  IMAP:      ❌ FAILED")
    
    print()
