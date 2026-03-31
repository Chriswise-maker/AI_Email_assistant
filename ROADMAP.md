# Roadmap: AI Email Triage Assistant

> Last reviewed: 2026-03-31
> Status: v0.5 — Working prototype, needs stability fixes before feature work

---

## Phase 1 — Stability & Bug Fixes

**Goal:** Make the existing features actually reliable. No new features until these are solid.
**Effort:** ~1 day

### Critical (data loss / broken functionality)

- [x] **Fix mark_seen timing in backend.py**
  - **Bug:** `mark_seen=True` at fetch time (line 144) marks emails as read before LLM analysis. If analysis fails or app crashes, emails are silently lost from the unseen queue.
  - **Fix:** Change to `mark_seen=False`. After successful analysis + rule application, explicitly call `mailbox.flag(uid, '\\Seen', True)`. On failure, email stays unread for next run.
  - **Files:** `backend.py` (lines 144, 173, ~252)

- [x] **Fix Claude system prompt handling in llm_providers.py**
  - **Bug:** System prompt is concatenated into the user message (line 127) instead of using Claude's `system` parameter. Weakens instruction-following.
  - **Fix:** Move system prompt to `system` parameter in `params`. Same fix for Gemini — use `system_instruction` parameter on `GenerativeModel`.
  - **Files:** `llm_providers.py` (ClaudeProvider lines 122-130, GeminiProvider lines 103-107)

- [x] **Fix Claude model detection for thinking/effort**
  - **Bug:** Hardcoded string matching (line 136) doesn't match `claude-sonnet-4-6` (the model actually in config). Thinking mode is never activated.
  - **Fix:** Remove model-gating entirely. If `thinking_level` is medium/high in config, always pass thinking params. Let the API reject if unsupported. Or use a simple version check (model contains `claude` and not `claude-3-5` or older).
  - **Files:** `llm_providers.py` (lines 136-143)

- [x] **Update stale model name in config.yaml**
  - **Bug:** `claude-sonnet-4-5` should be `claude-sonnet-4-6`.
  - **Files:** `config.yaml` (line 19)

### Important (functionality not working as configured)

- [x] **Enforce fetch_limit**
  - **Bug:** `fetch_limit` is read from config (line 99) but never applied. All unseen emails are fetched.
  - **Fix:** Slice the email list: `emails = emails[:fetch_limit]`
  - **Files:** `backend.py` (after line 144)

- [x] **Pass max_body_chars from config to clean_email_body()**
  - **Bug:** Hardcoded 3000 char limit ignores config value.
  - **Fix:** Read `settings.get("max_body_chars", 3000)` and pass to `clean_email_body()`.
  - **Files:** `backend.py` (lines 99, 151)

- [x] **Fix YAML save destroying system_prompt formatting**
  - **Bug:** `yaml.safe_dump` collapses the multiline `|` block scalar into a single line.
  - **Fix:** Use `default_flow_style=False` and `default_style='|'` for string fields, or use `ruamel.yaml` which preserves formatting. Simplest: use `yaml.dump` with a custom representer for long strings.
  - **Files:** `utils.py` (line 22), possibly `requirements.txt`

- [x] **Make file paths absolute**
  - **Bug:** `daily_briefing.md`, `debug_logs.json`, `config.yaml`, `.env` all use relative paths. Breaks if CWD differs.
  - **Fix:** Define `PROJECT_ROOT = Path(__file__).parent` in `utils.py`. Derive all paths from it.
  - **Files:** `utils.py`, `backend.py`, `app.py`

### Minor

- [x] **Add basic retry logic for LLM failures**
  - Single retry with 2s delay on provider `None` return. Prevents transient API errors from skipping emails.
  - **Files:** `backend.py` (around line 154)

- [x] **Restore debug viewer tab in UI**
  - Tab was removed during UI redesign. Add it back as the 4th tab.
  - Wire up `debug_logs.json` reading (the logging code may also need restoration in `backend.py`).
  - **Files:** `app.py`, `backend.py`

---

## Phase 2 — Core Features (Make It Actually Usable)

**Goal:** Turn the prototype into something you'd leave running daily.
**Effort:** ~3-5 days
**Prerequisite:** Phase 1 complete

### Email History & Search

- [ ] **Add SQLite database for email history**
  - Store every processed email: uid, account, sender, subject, category, priority, summary, timestamp, raw_analysis
  - Replace `daily_briefing.md` as the data source for the dashboard (keep briefing as optional export)
  - Add search/filter by sender, subject, category, date range in dashboard
  - **New file:** `database.py` (schema, CRUD operations)
  - **Modified:** `backend.py` (write to DB after analysis), `app.py` (query DB instead of parsing markdown)

### Background Scheduler

- [ ] **Add APScheduler for automatic triage runs**
  - Configurable interval in settings (e.g., every 15 min, every hour)
  - Show "last run" and "next run" timestamps in sidebar
  - Option to enable/disable scheduler from UI
  - **New dependency:** `apscheduler`
  - **Modified:** `app.py` (scheduler init, UI controls), `config.yaml` (schedule settings)

### Rules Editor in UI

- [ ] **Make category→action rules editable in the Settings tab**
  - Currently only editable by hand-editing `config.yaml`
  - Add a grid/table: category | action dropdown (flag, mark_read, delete, no_action)
  - Save button updates config
  - **Files:** `app.py` (Settings tab, ~line 497)

### Error Recovery

- [ ] **Track failed emails and allow retry**
  - Store failed email UIDs + error reason in DB or session state
  - Show "Failed Emails" section in dashboard with retry button
  - Failed emails should NOT be marked as seen (Phase 1 fix enables this)
  - **Files:** `backend.py`, `app.py`

### Desktop Notifications

- [ ] **Notify user on priority 4-5 emails**
  - Use `plyer` or native macOS `osascript` for desktop notifications
  - Only fire after triage run completes, if high-priority emails were found
  - Configurable: on/off in settings
  - **New dependency:** `plyer` (or use subprocess for macOS native)
  - **Files:** `backend.py` (after processing), `app.py` (settings toggle)

---

## Phase 3 — Intelligent Assistant

**Goal:** Evolve from a categorizer into an actual email assistant.
**Effort:** ~1-2 weeks
**Prerequisite:** Phase 2 complete (especially DB)

### Draft Reply Generation

- [ ] **Add LLM-powered draft replies**
  - New button on each email card: "Draft Reply"
  - LLM generates a reply based on email content + user-configurable tone/style
  - Draft shown in an editable text area
  - Save to IMAP Drafts folder via IMAP APPEND
  - **New system prompt:** separate prompt for reply generation (different from categorization)
  - **Files:** `llm_providers.py` (new method `generate_reply()`), `backend.py` (IMAP draft save), `app.py` (reply UI)

### SMTP Integration

- [ ] **Send emails directly from the app**
  - Configure SMTP server per account (often same host as IMAP)
  - Send drafted replies
  - Confirmation step before sending
  - **New file:** `smtp_handler.py`
  - **Modified:** `config.yaml` (smtp_server per account), `app.py` (send button)

### Smart Sender Recognition

- [ ] **VIP / known sender list**
  - User maintains a list of important senders (or auto-detect from "Personal" category)
  - VIP emails always get priority boost
  - Visual indicator in dashboard
  - **Files:** `config.yaml` (vip_senders list), `backend.py` (priority adjustment), `app.py` (VIP badge)

### Adaptive Learning

- [ ] **Learn from user corrections**
  - If user re-categorizes an email in the UI, store the correction
  - Feed corrections into future LLM prompts as few-shot examples
  - Track accuracy over time
  - **Requires:** Phase 2 DB for storing corrections
  - **Files:** `database.py` (corrections table), `backend.py` (inject examples into prompt), `app.py` (re-categorize UI)

### Conversation Threading

- [ ] **Group related emails into threads**
  - Use `In-Reply-To` and `References` headers from IMAP
  - Display as collapsible thread in dashboard
  - Thread-level summary (summarize entire conversation, not just latest email)
  - **Files:** `backend.py` (header extraction), `database.py` (thread_id column), `app.py` (thread view)

---

## Phase 4 — Production Polish

**Goal:** Make it deployable, maintainable, and robust.
**Effort:** ~1 week
**Prerequisite:** Core features stable

### SDK & Dependency Updates

- [ ] **Migrate Gemini to `google.genai` SDK**
  - `google-generativeai` is deprecated. Replace with `google-genai`.
  - Update `GeminiProvider` class, test thinking_level support.
  - **Files:** `llm_providers.py`, `requirements.txt`

- [ ] **Pin dependency versions**
  - Replace `>=` with `==` in requirements.txt for reproducible builds.
  - Add `requirements-dev.txt` for test dependencies.

### Testing

- [ ] **Add pytest test suite**
  - `tests/test_normalize_category.py` — exhaustive category fuzzy matching tests
  - `tests/test_clean_email_body.py` — HTML stripping, truncation, edge cases
  - `tests/test_apply_rules.py` — mock IMAP, verify flag/mark_read calls
  - `tests/test_llm_providers.py` — mock API responses, verify JSON parsing
  - `tests/test_briefing.py` — markdown generation, prepend logic
  - `tests/test_config.py` — load/save roundtrip, multiline string preservation
  - **New files:** `tests/` directory, `conftest.py` with fixtures
  - **New dependency:** `pytest`, `pytest-mock`

### Deployment

- [ ] **Dockerfile + docker-compose.yml**
  - Single container: Streamlit app + scheduler
  - Volume mounts for `.env`, `config.yaml`, DB file
  - Health check endpoint

- [ ] **CI/CD with GitHub Actions**
  - Run tests on push
  - Lint with ruff
  - Build Docker image on tag

### Security Improvements

- [ ] **OAuth2 for Gmail**
  - Replace app passwords with proper OAuth2 flow
  - Store refresh tokens encrypted
  - **New file:** `oauth_handler.py`

- [ ] **Encrypt stored credentials**
  - Encrypt `.env` values at rest using `cryptography.fernet`
  - Decrypt on load with a master password or OS keychain

### Rate Limit Handling

- [ ] **Track API usage per provider**
  - Count tokens/requests per provider per day
  - Warn in UI when approaching limits
  - Auto-fallback to secondary provider when primary is exhausted
  - **Files:** `llm_providers.py` (usage tracking), `app.py` (usage display), `config.yaml` (fallback_provider)

---

## Non-Goals (Explicitly Out of Scope)

These are things we're **not** building:
- **Multi-user / auth system** — this is a personal tool, not SaaS
- **Mobile app** — Streamlit is desktop-first, and that's fine
- **Real-time push notifications from IMAP IDLE** — polling on a schedule is good enough
- **Email client replacement** — this is a triage/assistant layer, not a full client
- **Custom ML model training** — we use LLM APIs, not local models

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-03-31 | File-based storage → SQLite (Phase 2) | Briefing markdown doesn't support search/filter, grows unbounded |
| 2026-03-31 | APScheduler over cron | Keeps everything in-process, configurable from UI |
| 2026-03-31 | Fix bugs before features | mark_seen bug can lose emails — can't build on a broken foundation |
| 2026-03-31 | Keep Streamlit (no framework switch) | Good enough for personal use, rewriting UI is waste of time |
| 2026-03-31 | No multi-user auth | Personal tool, complexity not justified |
