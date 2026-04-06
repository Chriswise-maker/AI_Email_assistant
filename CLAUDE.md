# AI Email Triage Assistant

## Project Overview
An email triage assistant that connects to IMAP accounts, fetches unread emails, analyzes them with LLMs, categorizes/prioritizes them, and applies rules.

## Tech Stack
- **Email**: imap-tools (IMAP protocol)
- **LLM Providers**: Groq, DeepSeek (OpenAI-compatible), Google Gemini, Anthropic Claude
- **Config**: YAML (`config.yaml`) + dotenv (`.env`)
- **Storage**: SQLite (`emails.db`), `debug_logs.json`
- **Python**: 3.11+

## Architecture

```
backend.py (email processing pipeline)
  -> llm_providers.py (LLM abstraction layer)
  -> utils.py (config/env helpers)
  -> database.py (SQLite persistence)
```

### Key Files
| File | Purpose |
|---|---|
| `backend.py` | `process_emails()` orchestrator, IMAP ops, rule execution |
| `llm_providers.py` | Abstract `LLMProvider` + Groq/DeepSeek/Gemini/Claude implementations |
| `database.py` | SQLite email history — schema, CRUD, search |
| `utils.py` | `load_config`, `save_config`, env variable read/write |
| `config.yaml` | Accounts, providers, categories, rules, system prompt |

### Data Flow
1. `process_emails()` loads config, connects to each enabled IMAP account
2. Fetches unseen emails, cleans HTML bodies via BeautifulSoup
3. Sends each email to selected LLM provider for analysis
4. LLM returns JSON: `{category, priority (1-5), summary}`
5. `normalize_category()` fuzzy-matches LLM output to canonical categories
6. `apply_rules()` flags/marks-read based on category->action mappings

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
- Print to stdout for debugging

### Important Constraints
- **Never remove email data** — if an operation might lose emails, add safety checks
- `.env` file is the single source of truth for secrets — never log or display API keys/passwords
- `config.yaml` gets written by the UI — changes must survive `yaml.safe_dump` (be careful with multiline strings)
- All file paths should be absolute or relative to project root
- **NEVER overwrite `system_prompt` in `config.yaml`** — it has been deliberately crafted (bullet-point format, bilingual, bolded key info). Any task touching `config.yaml` must preserve the `system_prompt` field exactly as-is.

### LLM Provider Implementation Pattern
Each provider extends `LLMProvider` ABC and implements `analyze_email(email_content, system_prompt, model) -> dict`.
Must return `{"category": str, "priority": int, "summary": str}` or `None` on failure.
When adding a new provider:
1. Add class in `llm_providers.py`
2. Add `elif` in `get_provider()` factory
3. Add config entry in `config.yaml` under `providers:`

### Testing
- `test_connections.py` — manual connectivity check (IMAP + LLM)
- No pytest suite yet — when adding tests, put them in a `tests/` directory
- To test without modifying emails: set `dry_run: true` in config.yaml

## Known Bugs (see ROADMAP.md for fix plan)
- Gemini `thinking_level` config is hypothetical — not verified against current SDK
