# AI Email Assistant

An intelligent email triage system with a web UI, powered by multiple LLM providers (Groq, DeepSeek, Gemini, Claude). It fetches unread mail over IMAP, categorizes and prioritizes it with an LLM, applies rules, stores everything in SQLite, and presents the results as a "daily briefing" in your browser.

## Features

- **Daily Briefing UI**: Flask + vanilla-JS single-page app — emails grouped into *Needs Attention* (priority ≥ 4), *Noted* (3), and *Quiet* (≤ 2)
- **Multi-Provider LLM Support**: Groq, DeepSeek, Google Gemini, or Anthropic Claude — switchable from the Settings page
- **Automatic Categorization**: Security, Bills & Invoices, Orders & Shipping, Newsletters, Personal, Notifications, Spam, Other
- **Priority Scoring**: 1–5 priority per email
- **Bullet-Point Summaries**: 2–4 scannable bullets with bolded key info (amounts, codes, deadlines), written in the email's original language
- **Email History**: every processed email is stored in SQLite (`emails.db`) — searchable across runs from the UI
- **Draft Replies**: generate an LLM reply draft for any email from the briefing
- **Rule-Based Actions**: flag, mark read, delete, or no action per category
- **Multi-Account IMAP**: any IMAP-compliant provider, multiple accounts

## Quick Start

### Prerequisites

- Python 3.11+
- An IMAP email account (GMX, Web.de, Gmail, …)
- API key for at least one LLM provider

### Installation

1. **Install dependencies**
   ```bash
   cd /path/to/AI_Email_assistant
   pip install -r requirements.txt
   ```

2. **Configure secrets**

   Secrets live in a user-level file **outside the repo**: `~/.config/ai-email-assistant/.env`
   (this survives git operations and worktree switches).

   ```bash
   mkdir -p ~/.config/ai-email-assistant
   cp .env.example ~/.config/ai-email-assistant/.env
   ```

   Then add your credentials:
   ```
   # LLM Provider API Keys (at least one required)
   GROQ_API_KEY=your_groq_key_here
   ANTHROPIC_API_KEY=your_claude_key_here
   GEMINI_API_KEY=your_gemini_key_here

   # Email Account Passwords — one per account id (PASSWORD_<ID>)
   PASSWORD_GMX=your_email_password_here
   ```

3. **Configure email accounts**

   Edit `config.yaml` (or add accounts later from the Settings page):
   ```yaml
   accounts:
     - id: GMX
       email: your.email@gmx.net
       server: imap.gmx.net
       enabled: true
       provider: imap
   ```

4. **Run the app**
   ```bash
   python server.py
   ```
   Open **http://localhost:5001**, then hit the run button to start a triage.

   > ⚠️ The server binds locally with Flask debug mode on — for personal/local use only.
   > Do not expose the port to a network.

## How It Works

1. **Run**: the UI starts a triage in a background thread and polls for status
2. **Fetch**: unread emails from the last `max_email_age_days` (default 30) are fetched per account, newest first, up to `fetch_limit`
3. **Analyze**: each email body is cleaned and sent to the active LLM
4. **Categorize**: the LLM returns `{category, priority, summary}` as JSON
5. **Apply Rules**: configured action runs (flag / mark read / delete / no action)
6. **Mark Processed**: emails are marked as read so they aren't re-processed
7. **Persist**: results are upserted into SQLite (`emails.db`, unique per `uid` + account)
8. **Brief**: the frontend renders the latest run as the daily briefing

## Configuration

Most day-to-day settings (provider, model, fetch limit, dry run, accounts) are editable from the **Settings page in the UI**. The full configuration lives in `config.yaml`:

```yaml
providers:
  claude:
    api_key_env: ANTHROPIC_API_KEY
    model: claude-haiku-4-5-20251001
    thinking_level: medium   # low | medium | high

settings:
  provider: claude           # active provider
  fetch_limit: 50            # max emails per account per run
  max_email_age_days: 30     # ignore unread mail older than this
  max_body_chars: 3000       # truncate bodies sent to the LLM
  dry_run: false

rules:
  Security: flag
  Newsletters: mark_read
  Notifications: mark_read
  Spam: mark_read
  # everything else: no_action
```

> **Note**: the `system_prompt` in `config.yaml` is deliberately crafted
> (bullet format, bilingual, bolded key info) — don't overwrite it.

## Troubleshooting

### "Analysis Failed" errors
- **Quota exceeded**: switch provider in Settings or wait for the quota reset
- **Invalid API key**: check `~/.config/ai-email-assistant/.env`
- The failure reason is surfaced in the run result and `debug_logs.json`

### Emails being re-processed
- Processed emails are marked *seen*; manually marking them unread re-queues them for the next run

### Gemini rate limits
Free-tier Gemini has strict daily quotas — prefer Claude or Groq for regular use.

## File Structure

```
AI_Email_assistant/
├── server.py              # Flask API + async triage runner (entry point)
├── templates/
│   └── index.html         # Single-page frontend (no build step)
├── backend.py             # process_emails() orchestrator, IMAP ops, rules
├── llm_providers.py       # LLM provider implementations (analyze + draft reply)
├── database.py            # SQLite schema, CRUD, search (emails.db)
├── utils.py               # Config + secrets helpers
├── config.yaml            # Accounts, providers, rules, system prompt
├── ROADMAP.md             # Known bugs / planned work
├── requirements.txt       # Python dependencies
└── .env.example           # Template for ~/.config/ai-email-assistant/.env
```

## License

MIT License — feel free to use and modify as needed.
