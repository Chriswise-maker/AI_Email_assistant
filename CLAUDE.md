# AI Email Triage Assistant

## Project Overview
A Flask-based email triage assistant that connects to IMAP accounts, fetches unread emails, analyzes them with LLMs, categorizes/prioritizes them, applies rules, stores history in SQLite, and serves a single-page HTML/JS frontend styled as a "daily briefing".

## Tech Stack
- **Backend API**: Flask (`server.py`, runs on `http://localhost:5001`)
- **Frontend**: Single-page HTML/JS in `templates/index.html` (no framework — vanilla JS, Material Symbols, Fraunces/Work Sans/IBM Plex Mono typography)
- **Email**: `imap-tools` (IMAP protocol)
- **LLM Providers**: Groq, DeepSeek (OpenAI-compatible), Google Gemini, Anthropic Claude
- **Config**: YAML (`config.yaml`) + dotenv (secrets live in `~/.config/ai-email-assistant/.env`)
- **Storage**: SQLite (`emails.db`) for history; `daily_briefing.md` is a legacy export; `debug_logs.json` for structured run logs
- **Python**: 3.11+

## Architecture

```
templates/index.html (SPA — vanilla JS, polls /api/triage/status)
        │
        ▼  fetch()
server.py (Flask API)
  ├─ /api/briefing        latest run + grouped emails
  ├─ /api/archive         past runs
  ├─ /api/search          full-text search across history
  ├─ /api/triage[/status] start + poll async triage
  ├─ /api/settings/*      provider, model, fetch-limit, dry-run, accounts
  ├─ /api/draft-reply     LLM reply generation
  └─ /api/delete/<id>     remove from DB + IMAP
        │
        ├─► backend.py    process_emails() orchestrator, IMAP ops, draft gen, IMAP delete
        │     └─► llm_providers.py  LLMProvider ABC + Groq/DeepSeek/Gemini/Claude
        ├─► database.py   SQLite schema, CRUD, search (emails.db at project root)
        └─► utils.py      load_config, save_config, env/password helpers, PROJECT_ROOT
```

**Note:** `app.py` (842 lines of Streamlit) is **dead code** — the Flask/HTML stack replaced it and nothing imports it. Safe to delete; kept around for now as reference.

### Key Files
| File | Purpose | Lines |
|---|---|---|
| `server.py` | Flask API + page route, async triage runner via threading | ~450 |
| `templates/index.html` | Single-page frontend (HTML + CSS + JS, no build step) | ~1620 |
| `backend.py` | `process_emails()`, `get_reply_draft()`, `delete_email_from_imap()`, briefing append | ~495 |
| `llm_providers.py` | `LLMProvider` ABC with `analyze_email()` + `draft_reply()` per provider | ~255 |
| `database.py` | SQLite schema + CRUD (emails, triage_runs), search, init-on-import | ~260 |
| `utils.py` | YAML load/save with block-scalar representer, `.env` helpers, `PROJECT_ROOT` | ~90 |
| `config.yaml` | Accounts, providers, categories, rules, system prompt | ~70 |
| `app.py` | **DEAD** — old Streamlit UI, unused by the Flask stack | ~840 |

### Data Flow
1. User clicks run (rail button or mobile FAB) → `POST /api/triage` starts a background thread
2. Frontend polls `GET /api/triage/status` every 1.5s
3. `process_emails()` loads config, calls `create_run()` → gets `run_id`
4. For each enabled account: IMAP login, fetch `AND(seen=False, date_gte=<cutoff>)` with `mark_seen=False`
5. Sort newest-first, slice to `fetch_limit`
6. Per email: clean body → LLM `analyze_email()` (with one retry on None)
7. LLM returns `{category, priority (1-5), summary}` — summary is 2-4 `•` bulleted lines, bolded key info, same language as email
8. `normalize_category()` fuzzy-matches to canonical categories
9. `apply_rules()` applies `flag` / `mark_read` / `delete` / `no_action`; then explicit `mailbox.flag(uid, '\\Seen', True)`
10. `save_email()` upserts into SQLite (unique on `uid+account`)
11. `append_to_briefing()` prepends markdown to `daily_briefing.md` (legacy)
12. `finish_run()` writes totals; frontend reloads `/api/briefing`
13. Emails grouped into `attention` (p≥4), `noted` (p=3), `quiet` (p≤2) for rendering

### Canonical Categories
Security, Bills & Invoices, Orders & Shipping, Newsletters, Personal, Notifications, Spam, Other

### Config Patterns
- LLM API keys: env var `{PROVIDER}_API_KEY` (e.g., `ANTHROPIC_API_KEY`)
- Email passwords: env var `PASSWORD_{ACCOUNT_ID}` (e.g., `PASSWORD_GMX`)
- Active provider: `settings.provider` in `config.yaml`
- Secrets file lives at `~/.config/ai-email-assistant/.env` (NOT in the repo — survives worktree switches and git operations)

## Development Rules

### Code Style
- Python, no type stubs needed — inline type hints where they add clarity
- LLM providers: return `None` on failure and set `self.last_error` (surfaced in `stats["details"]`)
- Backend: increment `stats["errors"]` / `stats["skipped"]` accordingly; never raise out of the per-email loop
- Print to stdout for operational logs; write structured entries via `write_debug_log()`

### Important Constraints
- **Never lose emails** — fetch with `mark_seen=False`; only flag Seen after successful analysis + rule application. Failed emails must stay unread for the next run.
- **NEVER overwrite `system_prompt` in `config.yaml`** — it's been deliberately crafted (bullet-point format, bilingual, bolded key info). Any task touching `config.yaml` must preserve it exactly. The custom YAML block-scalar representer in `utils.py` helps but don't rely on it alone — re-read before writing.
- `.env` at `~/.config/ai-email-assistant/.env` is the single source of truth for secrets — never log or display API keys/passwords
- All file paths flow through `PROJECT_ROOT` (from `utils.py`) — never use bare relative paths
- `daily_briefing.md` is append-only (newest prepended). It's now a legacy export — SQLite is source of truth
- Delete is irreversible — no trash table yet. Always confirm in UI before `/api/delete`

### LLM Provider Implementation Pattern
Each provider extends `LLMProvider` (ABC) and implements:
- `analyze_email(email_content, system_prompt, model) -> dict | None`
- `draft_reply(email_context, instruction, model) -> str | None`

`analyze_email` must return `{"category": str, "priority": int, "summary": str}`. On failure, return `None` AND set `self.last_error`.

When adding a new provider:
1. Add class in `llm_providers.py` (implement both methods)
2. Add `elif` in `get_provider()` factory
3. Add config entry in `config.yaml` under `providers:`
4. Add entry to `_PROVIDER_MODELS` in `server.py` (the UI model dropdown)
5. Add lowercase name to the provider dropdown in `loadSettings()` in `templates/index.html`

### Testing
- `test_connections.py` — manual connectivity check (IMAP + LLM)
- No pytest suite yet — when adding, put tests in a `tests/` directory
- To test without modifying emails: set `dry_run: true` in config.yaml (or toggle from Settings page)

### Running the App
```bash
# From project root:
source venv/bin/activate
python server.py
# Frontend at http://localhost:5001
```

## Known Bugs / Tech Debt (see ROADMAP.md)
- `debug=True` in `server.py:448` — Werkzeug debugger is an RCE vector if port ever exposed. Must be `False` in any non-dev context.
- YAML block-scalar representer in `utils.py` doesn't always fire — `config.yaml` currently shows `system_prompt` as an escape-sequenced single-line string. Investigate whether the representer is registered on the right Dumper class.
- `_PROVIDER_MODELS` in `server.py` and `config.yaml` defaults have drifted (e.g., Gemini 2.0 vs 3 preview). Consolidate source of truth.
- `_triage` is module-global dict — if Flask reloads mid-triage (debug mode), status is lost forever and frontend polls forever. Add timeout on `pollTriage()` in the JS.
- Gemini `thinking_level` still hypothetical — not verified against current SDK.
- `app.py` is orphaned Streamlit code — delete or move to `legacy/`.
- `utils_backup.py` empty; `walkthrough.md` / `task.md` stale.
- `debug_logs.json` capped at 500 entries but no UI exposes it (old debug tab was on the Streamlit app).
