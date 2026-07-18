# Roadmap: AI Email Triage Assistant

> Last reviewed: 2026-07-18
> Status: v0.9 — Flask UI merged to main; two code-review passes + a summary-quality redesign shipped. Runs and renders cleanly. Still not a daily driver: it doesn't run without you opening it.

---

## ▶ Next Session Starts Here

**The one thing missing that matters: the system doesn't run without the user.** It's a tool you visit, not a system that works before you show up. The next build closes that gap. Build **Tier 1 first, as one focused session:**

1. **Scheduled triage** — runs itself (e.g. 07:00 / 17:00) via launchd or an in-process scheduler; server as a background service.
2. **Emailed briefing** — email the digest to the user so it lands on their phone and is visible daily (judged more valuable than desktop notifications *because* it reaches the phone). One SMTP function.
   - **Prerequisites (do as part of Tier 1):** `debug=True`→off + real WSGI server (`waitress`); fix the triage-start race (two rapid `POST /api/triage` start two concurrent runs).

Then Tier 2 (Drafts-folder save, per-sender correction learning, one-click unsubscribe) and Tier 3 (chat-over-history, deadline "coming up" list, archive action). Detail lives in Phase 2/3 below. **Non-goal:** never build a mail client — identity is triage + briefing.

---

## Where We Are

**Shipped (through commit `8a12716`, on `main` + GitHub):**
- Flask API + custom HTML/JS SPA (`server.py`, `templates/index.html`) — replaced the old Streamlit `app.py`. Entry point: `python server.py` → http://localhost:5001
- SQLite email history (`emails.db`) with search + archive of past runs; auto-migrating schema
- **Schema v2 analysis** — LLM receives From/Subject/Date and returns `{category, priority, action, key_fact, deadline, summary}`. Cards lead with the extracted key fact + action chip; empty summaries allowed (thin emails stay quiet). Backed by a before/after benchmark on 15 real emails.
- Two code-review passes fixed: working dry-run toggle, tz-sort crash, config-wipe guard, strict provider resolution (no credential leak), retry-safe `apply_rules`, safer `normalize_category`
- Draft reply generation (LLM) with per-email instruction + clipboard copy
- Delete email (removes from DB + IMAP)
- Settings UI: provider, model, fetch-limit, dry-run, add-account, per-account enable toggle
- Debug logging to `debug_logs.json` (capped at 500, self-healing on corruption)

**Missing to be a daily driver** (priority order — see ▶ Next Session above):
- Auto-run (scheduler) + emailed briefing ← **do first**
- Drafts → IMAP Drafts folder (currently dead-end copy-paste)
- Correction / per-sender learning loop
- One-click unsubscribe (`List-Unsubscribe` header)

---

## Phase 1 — Stability & Bug Fixes ✅ COMPLETE

All items closed. See git log for details. Summary of what was fixed:
- `mark_seen` timing (no more silent email loss)
- Claude `system` parameter + extended thinking with proper `budget_tokens`
- Gemini `system_instruction` parameter
- `fetch_limit` + `max_body_chars` now actually enforced
- YAML multiline representer added (`utils.py`)
- `PROJECT_ROOT`-based absolute paths
- LLM retry logic (1 retry, 2s delay)
- Structured debug logging restored (`write_debug_log()`)

---

## Phase 1.5 — Known Issues & Tech Debt 🔧

**Reconciled with two code-review passes (2026-07-18). Fixed items struck through; open items are what to clean up before / alongside more features.**

### Fixed this session ✅
- [x] Dry-run toggle was decorative (every "dry run" mutated the mailbox) — now reads `config.settings.dry_run`
- [x] tz-aware/naive email-date sort crash aborted whole accounts — `_email_sort_key()` coerces to UTC
- [x] Settings write could wipe the whole config (incl. `system_prompt`) on a parse error — `_mutate_config()` guard
- [x] Misconfigured provider leaked `GROQ_API_KEY` to the wrong endpoint — `_build_provider()` errors instead
- [x] `apply_rules` swallowed failures (email marked done anyway) — now leaves failed emails unread for retry
- [x] `normalize_category` mapped "not spam"→Spam — substring fallback removed, unknown→Other
- [x] `write_debug_log` dropped all entries forever after one corrupt write — self-heals now
- [x] `system_prompt` now stored as a readable YAML **block scalar** (the old representer-not-firing issue is resolved for this write path)
- [x] Stale docs / dead imports removed

### Critical (still open)

- [ ] **Flask `debug=True` in the serving path** — `server.py` `app.run(debug=True)`
  - Werkzeug debugger + auto-reload. RCE vector if the port is ever exposed via tunnel / VPN. Also the reloader is what makes `_triage` status stick.
  - **Fix:** default `debug=False`, optional `--debug` for dev, serve with `waitress`. **Do this as part of Tier 1.**

- [ ] **Delete-by-UID has no UIDVALIDITY check + no trash** — `server.py` `api_delete_email`, `backend.py` `delete_email_from_imap`
  - Riskiest remaining item. If a mailbox's UID space resets (UIDVALIDITY change), a stored UID points at a *different* message → the delete button removes the **wrong** email, irreversibly.
  - **Fix:** store UIDVALIDITY per account and re-validate before delete; add a trash table + 10s undo toast; default delete to DB-only with an explicit "also delete from server".

- [ ] **Triage-start race (TOCTOU)** — `server.py` `api_triage`
  - Two rapid `POST /api/triage` both pass the `if _triage["running"]` check → two concurrent `process_emails` runs. Especially relevant once a scheduler also triggers runs.
  - **Fix:** a lock/compare-and-set around the running flag (or persist run state in the DB). **Do this as part of Tier 1.**

### Important

- [ ] **`_triage` module-global state** — persist run status in the DB (`triage_runs.state`), add a poll timeout + Cancel in the JS.
- [ ] **Efficiency (per-email waste)** — `process_emails` downloads full bodies of *all* unseen mail before truncating to `fetch_limit` (use `fetch(limit=…)`); `write_debug_log` rewrites the whole JSON file per email (buffer per run or use JSONL); `database.py` opens a fresh SQLite connection per email.
- [ ] **`_PROVIDER_MODELS` drift** — `server.py` UI offers a `deepseek` option with no `config.yaml` entry (now errors clearly via `_build_provider`, so no longer dangerous, but the drift remains). Consolidate to one source.
- [ ] **No `tests/` suite** — convert this session's benchmark + verification scripts (normalize-category table, config-wipe guard, tz-sort, DB migration) to pytest.

### Minor

- [ ] **Gemini SDK deprecated** — migrate `google-generativeai` → `google.genai`; verify/remove the hypothetical `thinking_level` branch.
- [ ] **No pagination on archive** — `get_all_runs(limit=50)`; `emails.db` grows unbounded.
- [ ] **`debug_logs.json` has no UI** — add a viewer or drop the file.

---

## Phase 2 — The Two-Week Push to Daily Driver 🎯

**Goal:** Make it so the app runs itself, tells you about urgent things, and completes the reply workflow. After this, you actually use it every day instead of forgetting it's there.

### Week 1 — Actual Assistant Behavior

- [ ] **APScheduler for automatic triage runs** *(half day)*
  - Background scheduler in `server.py`, default 15-min interval, configurable from Settings
  - `scheduler.add_job(process_emails, 'interval', minutes=15, id='triage')`
  - Show "Last run: 2m ago · Next run: in 13m" in the rail / status dot tooltip
  - Toggle on/off in Settings
  - **Files:** `server.py`, `templates/index.html` (status display), `config.yaml` (schedule block)
  - **New dep:** `apscheduler`

- [ ] **macOS desktop notifications on priority ≥ 4** *(2 hours)*
  - Simplest: `subprocess.run(['osascript', '-e', f'display notification "{subject}" with title "{sender}"'])`
  - Fire once per triage run, summarizing urgent count: "3 urgent emails — click to open"
  - Clicking the notification opens `http://localhost:5001`
  - Toggle in Settings (`notify_on_urgent: true`)
  - **Files:** `backend.py` (after processing), `server.py` (settings endpoint), `templates/index.html` (toggle)

- [ ] **Save drafts to IMAP Drafts folder** *(half day)*
  - `mailbox.append(raw_msg.as_bytes(), '+Drafts', dt=None, flag_set=['\\Draft'])` (folder name varies per provider: `Drafts`, `INBOX.Drafts`, `[Gmail]/Drafts` — detect via `mailbox.folder.list()`)
  - Build RFC822 message with `In-Reply-To` + `References` for proper threading in user's email client
  - Replace "Copy" button with "Save to Drafts" (keep Copy as secondary)
  - **Files:** `backend.py` (new `save_draft_to_imap()`), `server.py` (new `/api/save-draft`), `templates/index.html` (button + success state)

- [ ] **Re-categorize / correction UI + few-shot learning** *(1 day)*
  - Click category badge on any email → dropdown with all canonical categories
  - On change: `POST /api/correct` → writes to new `corrections` table `(email_id, old_category, new_category, corrected_at)`
  - Before each `analyze_email()` call: fetch last 5 corrections, inject into system prompt as `"Examples of user corrections: [subject → category]"`
  - **Files:** `database.py` (corrections table + `get_recent_corrections()`), `backend.py` (inject into prompt), `server.py` (`/api/correct`), `templates/index.html` (dropdown UI)

- [ ] **VIP / sender rules** *(half day)*
  - New `sender_rules` table: `(pattern, action, priority_boost, category_override)`
  - Pattern can be full email or domain (`@company.com`)
  - Applied after LLM analysis: boost priority, override category, force-flag
  - Settings page: simple list editor (sender pattern + rule)
  - **Files:** `database.py`, `backend.py` (apply after `normalize_category`), `server.py` (CRUD endpoints), `templates/index.html` (Settings panel)

### Week 2 — Productization

- [ ] **Keyboard shortcuts** *(1 day)*
  - `j`/`k` — navigate emails, `e` — archive, `#` — delete, `r` — reply, `c` — re-categorize, `/` — focus search, `g b`/`g a`/`g s` — go to Briefing/Archive/Settings, `cmd+enter` — run triage
  - Hotkeys shown on `?` overlay
  - **Files:** `templates/index.html` (vanilla JS keydown listener)

- [ ] **Server-Sent Events for triage progress** *(half day)*
  - Replace 1.5s polling with `GET /api/triage/stream` returning SSE
  - Emit per-email updates: `data: {"progress": 3, "total": 50, "current": "Invoice from Strato"}\n\n`
  - Frontend shows live progress bar + current email subject
  - **Files:** `server.py` (SSE endpoint), `backend.py` (progress callback), `templates/index.html` (EventSource)

- [ ] **Menu bar app (`rumps` wrapper)** *(1 day)*
  - `rumps` menu bar icon with live badge count (urgent emails)
  - Menu items: Open Briefing, Run Triage Now, Pause/Resume, Quit
  - Runs `server.py` as subprocess; auto-starts on login via `launchctl` plist
  - **New files:** `menubar.py`, `com.user.ai-email-assistant.plist`
  - **New dep:** `rumps`

- [ ] **API key entry in Settings UI** *(2 hours)*
  - The Settings UI has no way to enter keys
  - Per-provider password field in Settings → writes to `~/.config/ai-email-assistant/.env`
  - Show green check next to providers with keys set (don't reveal the key)
  - **Files:** `server.py` (`/api/settings/api-key`), `templates/index.html` (Settings panel)

- [ ] **Fix Phase 1.5 regressions** *(half day)*
  - Close out the critical items above (`debug=False`, `_triage` persistence, YAML fix)

---

## Phase 3 — Beyond Daily Driver

### Workflow Completeness

- [ ] **SMTP send** — direct send of drafts with confirmation, not just save-to-drafts
- [ ] **Snooze** — "remind me tomorrow 9am", resurfaces in the briefing at that time
- [ ] **Bulk actions** — select many, archive/delete/move in one go (10s undo toast)
- [ ] **Archive** (vs. delete) — move to user's Archive folder, don't purge
- [ ] **Conversation threading** — group by `In-Reply-To` / `References`, thread-level summary

### Intelligence

- [ ] **Failed email retry queue** — surface skipped emails with retry button + error reason
- [ ] **Category editor** — add/remove/rename canonical categories from UI (regenerates the prompt)
- [ ] **Tone presets for drafts** — Professional / Warm / Terse / Match-sender's-tone
- [ ] **Cost / usage tracking** — per-provider token counts, daily spend estimate

### Polish

- [ ] **Dark mode** — CSS variable swap + persisted toggle
- [ ] **Rules editor in UI** — category→action mappings (currently YAML-only)
- [ ] **Progressive onboarding** — first-run wizard (add account → enter API key → test connection → run first triage)
- [ ] **Empty-state CTAs** — "No briefings yet" → big "Run your first triage" button

---

## Phase 4 — Production Polish

### SDK & Dependency Updates

- [ ] **Migrate Gemini to `google.genai`** — `google-generativeai` is deprecated
- [ ] **Pin dependency versions** — replace `>=` with `==` in `requirements.txt`, add `requirements-dev.txt`

### Testing

- [ ] **pytest suite** in `tests/`
  - `test_normalize_category.py` — exhaustive fuzzy matching
  - `test_clean_email_body.py` — HTML stripping, truncation, edge cases
  - `test_apply_rules.py` — mock IMAP, verify flag/mark_read calls
  - `test_llm_providers.py` — mock API responses, verify JSON + error paths
  - `test_database.py` — CRUD roundtrips, upsert on `uid+account`
  - `test_config.py` — load/save preserves multiline `system_prompt`
  - `test_server.py` — Flask test client for endpoints
  - **New deps:** `pytest`, `pytest-mock`

### Deployment

- [ ] **Proper daemon** — `launchctl` plist for macOS, `systemd` unit for Linux. No more "keep terminal open"
- [ ] **App packaging** — PyInstaller or py2app `.app` bundle, one double-click install
- [ ] **Optional Docker** — `Dockerfile` + `docker-compose.yml` with volume mounts
- [ ] **CI/CD** — GitHub Actions: ruff + pytest on PR, release build on tag

### Security

- [ ] **Replace Flask debug server** — `waitress` (pure Python, easy) or `gunicorn`
- [ ] **OAuth2 for Gmail** — app passwords are being phased out
- [ ] **Encrypt stored credentials** — `cryptography.fernet` + macOS Keychain master key
- [ ] **CSRF tokens** — if the Flask server ever gets exposed beyond localhost
- [ ] **Bind to `127.0.0.1` only** — verify server.py doesn't listen on 0.0.0.0

### Rate Limit Handling

- [ ] **Per-provider token/request tracking** — warn in UI when approaching limits
- [ ] **Automatic provider fallback** — primary exhausted → switch to secondary for the run

---

## Non-Goals (Explicitly Out of Scope)

- **Multi-user / auth system** — personal tool, not SaaS
- **Full email client replacement** — this is a triage/assistant layer; user still lives in Apple Mail / Gmail for compose + send + search
- **IMAP IDLE real-time push** — scheduler polling is good enough; IDLE adds state-machine complexity for marginal benefit
- **Custom ML model training** — LLM APIs are sufficient
- **Mobile-native app** — responsive web is good enough; if it becomes necessary, wrap the PWA

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-03-31 | File-based storage → SQLite | Briefing markdown doesn't support search/filter, grows unbounded |
| 2026-03-31 | APScheduler over cron | Keeps everything in-process, configurable from UI |
| 2026-03-31 | Fix bugs before features | `mark_seen` bug could lose emails — can't build on broken foundation |
| 2026-03-31 | No multi-user auth | Personal tool, complexity not justified |
| 2026-04-10 | **Adopt Flask + vanilla HTML/JS** | A custom frontend provides full interaction and design control with no frontend build step. Accepted cost: widgets and state management are hand-built. |
| 2026-04-22 | **Prioritize scheduler + notifications + IMAP draft save** | These three unlock "ambient assistant" UX — without them, the app is a batch report on demand |
| 2026-04-22 | **Re-categorize + few-shot corrections before more LLM features** | Trust is the binding constraint — users abandon assistants that misclassify without a fix loop |
| 2026-04-22 | **Menu bar app via `rumps`** over Electron / webview wrappers | Minimal deps, native macOS feel, Python-only toolchain |
| 2026-07-18 | **Merge `claude/jovial-satoshi` Flask UI to `main`; retire Streamlit** | The custom Flask + SPA is the real UI; committed the previously-untracked `server.py`/`templates/` so they couldn't be lost |
| 2026-07-18 | **Schema v2: decision-brief, not re-summary** | Benchmark on 15 real emails showed old summaries restated the subject for ~half the inbox and padded thin mail; new schema extracts a `key_fact` + `action` + `deadline`, allows empty summaries, and feeds sender/subject to fix blind classification |
| 2026-07-18 | **Prompt changes require: draft → benchmark on real mail → user approval → apply** | The `system_prompt` is a protected, load-bearing asset; changes must be measured, not guessed. This is the standing process. |
| 2026-07-18 | **Emailed briefing over desktop notifications as the priority-1 delivery** | A digest emailed to the user reaches their phone and makes the system visible daily with zero new infra; notifications are Mac-only and easy to miss |
