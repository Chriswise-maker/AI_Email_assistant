# Roadmap: AI Email Triage Assistant

> Last reviewed: 2026-04-22
> Status: v0.7 — Flask + HTML/JS frontend shipped; SQLite history + draft replies working. Not yet a daily driver: no auto-run, no notifications, drafts don't send.

---

## Where We Are

**Shipped:**
- Phase 1 stability fixes (all bugs closed)
- Flask API + custom HTML/JS SPA (replaced Streamlit entirely — `app.py` is now dead code)
- SQLite email history (`emails.db`) with search + archive of past runs
- Draft reply generation (LLM) with per-email instruction + clipboard copy
- Delete email (removes from DB + IMAP)
- Settings UI: provider, model, fetch-limit, dry-run, add-account, per-account enable toggle
- Debug logging to `debug_logs.json` (capped at 500 entries)

**Missing to be a daily driver:**
- Auto-run (scheduler)
- Notifications on urgent emails
- Drafts go to IMAP Drafts folder / SMTP send (currently dead-end copy-paste)
- Correction UI (re-categorize wrong assignments → learning loop)
- VIP / sender rules
- Keyboard shortcuts

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

## Phase 1.5 — Current Regressions & Tech Debt 🔧

**Bugs discovered in review that need cleanup before more features land.**

### Critical

- [ ] **Flask `debug=True` in production path** — `server.py:448`
  - Werkzeug debugger + auto-reload. RCE vector if the port is ever exposed via tunnel / VPN misconfig.
  - **Fix:** Default `debug=False`. Optional `--debug` flag for dev. Switch to `waitress` (simpler) or `gunicorn` for serving.

- [ ] **`_triage` module-global state** — `server.py:112`
  - If Flask auto-reloads (debug mode) or crashes mid-triage, status is stuck and frontend polls forever.
  - **Fix:** Persist status in DB (`triage_runs.state` column: `running`/`complete`/`failed`), add 10-minute timeout to `pollTriage()` in JS, surface a "Cancel" button.

### Important

- [ ] **YAML representer not firing on `system_prompt`** — `utils.py:22-29`, `config.yaml:48`
  - The block-scalar representer is registered but `system_prompt` still saves as escape-sequenced single-line quoted string. Likely `_yaml_dumper = yaml.SafeDumper` mutates the class globally but something else re-registers / the wrong Dumper is picked on some save paths.
  - **Fix:** Define a subclass (`class _BlockDumper(yaml.SafeDumper): pass`) and attach the representer to that specifically. Add a round-trip test in `tests/test_config.py`.

- [ ] **Model list drift** — `server.py:307` `_PROVIDER_MODELS` vs `config.yaml`
  - Gemini: UI offers `gemini-2.0-flash` / `gemini-2.5-pro-preview`; config default is `gemini-3-flash-preview`. Two sources of truth.
  - **Fix:** Move model list to `config.yaml` under `providers.<name>.available_models`, or to a single `models.py`. `server.py` reads from one place.

- [ ] **Delete is irreversible** — `server.py:423`
  - One misclick → permanent data loss (DB row + IMAP message).
  - **Fix:** Trash table with 30-day TTL. Show "Undo" toast in UI for 10s after delete. Move IMAP delete to a "purge trash" job.

- [ ] **Delete `app.py` (Streamlit dead code)** — 842 lines, unused since the Flask pivot. Move to `legacy/` or remove entirely. Confuses agents exploring the repo.

### Minor

- [ ] **Gemini `thinking_level` still hypothetical** — `llm_providers.py:143-149`. Verify against current SDK or remove the branch.
- [ ] **Retire `daily_briefing.md`** — SQLite is source of truth now. Make the markdown briefing an opt-in export, not an auto-append.
- [ ] **Clean up stale docs** — `walkthrough.md`, `task.md`, empty `utils_backup.py`.
- [ ] **No pagination on archive** — `get_all_runs(limit=50)`. Fine for now, but emails.db grows unbounded.
- [ ] **`debug_logs.json` has no UI** — old Streamlit debug tab is gone. Add `/api/debug-logs` + a Settings panel (or drop the file).

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
  - Regression from the Streamlit→Flask pivot — new UI has no way to enter keys
  - Per-provider password field in Settings → writes to `~/.config/ai-email-assistant/.env`
  - Show green check next to providers with keys set (don't reveal the key)
  - **Files:** `server.py` (`/api/settings/api-key`), `templates/index.html` (Settings panel)

- [ ] **Fix Phase 1.5 regressions** *(half day)*
  - Close out the critical items above (`debug=False`, `_triage` persistence, YAML fix, delete `app.py`)

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
| 2026-04-10 | **Streamlit → Flask + vanilla HTML/JS** | Streamlit's re-run model makes real interactivity painful; custom frontend gives full design control and better perf. Accepted cost: lose auto-generated widgets, have to hand-build everything |
| 2026-04-22 | **Prioritize scheduler + notifications + IMAP draft save** | These three unlock "ambient assistant" UX — without them, the app is a batch report on demand |
| 2026-04-22 | **Re-categorize + few-shot corrections before more LLM features** | Trust is the binding constraint — users abandon assistants that misclassify without a fix loop |
| 2026-04-22 | **Menu bar app via `rumps`** over Electron / webview wrappers | Minimal deps, native macOS feel, Python-only toolchain |
