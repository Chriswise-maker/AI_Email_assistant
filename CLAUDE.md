# AI Email Triage Assistant

## Project Overview
A Streamlit-based email triage assistant that connects to IMAP accounts, fetches unread emails, analyzes them with LLMs, categorizes/prioritizes them, applies rules, and generates daily briefings.

## Tech Stack
- **UI**: Streamlit (run with `streamlit run app.py`)
- **Email**: imap-tools (IMAP protocol)
- **LLM Providers**: Groq, DeepSeek (OpenAI-compatible), Google Gemini, Anthropic Claude
- **Config**: YAML (`config.yaml`) + dotenv (`.env`)
- **Storage**: File-based (no database yet) — `daily_briefing.md`, `debug_logs.json`
- **Python**: 3.11+

## Architecture

```
app.py (Streamlit UI)
  -> backend.py (email processing pipeline)
       -> llm_providers.py (LLM abstraction layer)
       -> utils.py (config/env helpers)
```

### Key Files
| File | Purpose | Lines |
|---|---|---|
| `app.py` | Streamlit dashboard — tabs: Dashboard, Accounts, Settings | ~510 |
| `backend.py` | `process_emails()` orchestrator, IMAP ops, briefing generation | ~330 |
| `llm_providers.py` | Abstract `LLMProvider` + Groq/DeepSeek/Gemini/Claude implementations | ~175 |
| `utils.py` | `load_config`, `save_config`, env variable read/write | ~68 |
| `config.yaml` | Accounts, providers, categories, rules, system prompt | ~67 |

### Data Flow
1. User clicks "Run Triage Now" in `app.py`
2. `process_emails()` loads config, connects to each enabled IMAP account
3. Fetches unseen emails, cleans HTML bodies via BeautifulSoup
4. Sends each email to selected LLM provider for analysis
5. LLM returns JSON: `{category, priority (1-5), summary}`
6. `normalize_category()` fuzzy-matches LLM output to canonical categories
7. `apply_rules()` flags/marks-read based on category->action mappings
8. `append_to_briefing()` writes results to `daily_briefing.md`
9. `app.py` parses briefing file and renders email cards in dashboard

### Canonical Categories
Security, Bills & Invoices, Orders & Shipping, Newsletters, Personal, Notifications, Spam, Other

### Config Patterns
- LLM API keys: env var `{PROVIDER}_API_KEY` (e.g., `ANTHROPIC_API_KEY`)
- Email passwords: env var `PASSWORD_{ACCOUNT_ID}` (e.g., `PASSWORD_GMX`)
- Active provider: `settings.provider` in config.yaml

## Development Rules

### Code Style
- Python, no type stubs needed — use inline type hints where they add clarity
- Error handling: return `None` from LLM providers on failure, increment `stats["errors"]` in backend
- Print to stdout for debugging (Streamlit captures stderr)

### Important Constraints
- **Never remove email data** — if an operation might lose emails, add safety checks
- `daily_briefing.md` is append-only (newest prepended). Never truncate it without user consent
- `.env` file is the single source of truth for secrets — never log or display API keys/passwords
- `config.yaml` gets written by the UI — changes must survive `yaml.safe_dump` (be careful with multiline strings)
- All file paths should be absolute or relative to project root — Streamlit may run from different CWDs

### LLM Provider Implementation Pattern
Each provider extends `LLMProvider` ABC and implements `analyze_email(email_content, system_prompt, model) -> dict`.
Must return `{"category": str, "priority": int, "summary": str}` or `None` on failure.
When adding a new provider:
1. Add class in `llm_providers.py`
2. Add `elif` in `get_provider()` factory
3. Add config entry in `config.yaml` under `providers:`
4. Add to `PROVIDERS` list in `app.py` settings tab

### Testing
- `test_connections.py` — manual connectivity check (IMAP + LLM)
- No pytest suite yet — when adding tests, put them in a `tests/` directory
- To test without modifying emails: set `dry_run: true` in config.yaml

### Running the App
```bash
# From project root:
source venv/bin/activate
streamlit run app.py
# Dashboard at http://localhost:8501
```

## Known Bugs (see ROADMAP.md for fix plan)
- `mark_seen=True` at fetch time means failed emails get marked as read and lost
- Claude provider ignores `system` parameter, stuffs system prompt into user message
- Claude model detection for thinking/effort uses hardcoded string matching that misses current models
- `fetch_limit` from config is read but never enforced
- `max_body_chars` from config is not passed to `clean_email_body()`
- `yaml.safe_dump` destroys multiline block scalars (system_prompt formatting)
- Debug viewer tab was removed from UI but debug logging code references remain
- Gemini `thinking_level` config is hypothetical — not verified against current SDK
