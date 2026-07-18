# Email assistant review — implementation plan

> **For agentic workers:** Implement task-by-task in order unless noted; checkboxes track progress.

**Goal:** Close the gaps from the code review: config/CLI usability, correct rule and read/unread semantics, safer failure handling, validated LLM output, hygiene (docs, gitignore, secrets), and optional persistence.

**Architecture:** Keep changes in `backend.py`, `llm_providers.py`, and `utils.py` cohesive; add a thin `cli.py` (or `__main__.py`) entry point; extract small helpers (`validate_llm_analysis`, `apply_rules` return type) to avoid sprawl. Prefer one clear `settings` block in `config.yaml` for new flags.

**Tech stack:** Python 3.11+, existing deps; optional `filelock` (or stdlib `fcntl` on POSIX only) for debug log safety.

---

## File map

| File | Role |
|------|------|
| `backend.py` | Effective `dry_run`, rule outcomes, `\Seen` semantics, stats payload, call validation |
| `llm_providers.py` | Normalize/validate JSON after parse; set `last_error` on validation failure |
| `utils.py` | Unchanged unless shared helpers move here |
| `cli.py` (new) or `__main__.py` | Parse args, load config, call `process_emails` |
| `test_connections.py` | Pass full `config` into `get_provider` |
| `config.yaml` | New settings keys; **replace real email with placeholder** in repo template |
| `.env.example` | Document any new env vars (e.g. `ALLOW_DELETE_RULE`) |
| `.gitignore` | `emails.db`, `debug_logs.json` |
| `README.md`, `CLAUDE.md` | Align with behavior; remove or qualify SQLite claims |
| `requirements.txt` | Add `filelock` if chosen for logs |
| `tests/` (new) | Unit tests for validation + `apply_rules` behavior (optional but recommended) |

---

## Phase 1 — Configuration and entry point (usability)

### Task 1.1: Effective `dry_run`

**Files:** `backend.py`, `README.md` (short note)

- [ ] **Step 1:** In `process_emails()`, after `load_config()`, compute  
  `effective_dry_run = dry_run or bool(settings.get("dry_run", False))`  
  (CLI/explicit arg overrides file if you prefer: document `explicit False` vs unset — recommended: **function arg `None` means “use config”**, `True`/`False` forces).
- [ ] **Step 2:** Replace all internal uses of `dry_run` with `effective_dry_run` (logging, `apply_rules`, `\Seen`).
- [ ] **Step 3:** Document in README: precedence (CLI > config or arg > config — match implementation).

### Task 1.2: CLI / module entry point

**Files:** `cli.py` (new) or `email_assistant/__main__.py`, `README.md`

- [ ] **Step 1:** Add `main()` that loads config, reads optional `--dry-run` / `--dry-run=false`, calls `process_emails(...)`, prints JSON or formatted summary of returned `stats`.
- [ ] **Step 2:** Wire `python -m` (e.g. package `email_assistant` with `__main__.py`) **or** `run_triage.py` at repo root — pick one and document the canonical command in README.
- [ ] **Step 3:** Run manually once (no keys needed for import check: `python -c "import backend"`).

---

## Phase 2 — Rule semantics and IMAP stability (core behavior)

### Task 2.1: `apply_rules` returns status

**Files:** `backend.py`

- [ ] **Step 1:** Change `apply_rules` to return `bool` (success) or a small `dataclass`/`NamedTuple` with `(ok: bool, error: str | None)`.
- [ ] **Step 2:** On IMAP exception, return failure; **do not** swallow without surfacing to caller.
- [ ] **Step 3:** Remove duplicate `\Seen` inside `apply_rules` for `mark_read` if you centralize marking (see Task 2.2) to avoid double-flagging — or keep one place only.

### Task 2.2: When to set `\Seen` (fix semantics)

**Files:** `backend.py`, `config.yaml` example in README, `CLAUDE.md`

- [ ] **Step 1:** **Remove** the unconditional `mailbox.flag(uid, '\\Seen', True)` after every success.
- [ ] **Step 2:** Set `\Seen` only according to **explicit rules**:
  - `mark_read` → set `\Seen` (in `apply_rules` or immediately after success in one block).
  - `flag` → set `\Flagged` only; **do not** set `\Seen` unless product asks for both (default: **not** seen, so flagged security mail stays unread in the inbox).
  - `no_action` → no flags.
  - `delete` → delete (see Phase 4 safeguards).
- [ ] **Step 3:** Audit default `rules:` in `config.yaml` so categories that should disappear from “unread” use `mark_read` (e.g. Newsletters, Notifications, Spam already do).
- [ ] **Step 4:** Document **breaking change**: previously everything was marked read; now only `mark_read` (and delete) changes read state as above. Add migration note in README.

### Task 2.3: Stats and success only when rules succeed

**Files:** `backend.py`

- [ ] **Step 1:** If analysis succeeds but `apply_rules` fails: increment `stats["errors"]` (or a new `stats["rule_errors"]`), append detail with IMAP error, **do not** count as `processed` (or count as `processed_with_errors` — pick one and document).
- [ ] **Step 2:** Do not write “success” debug log entries for failed rule application.

### Task 2.4: Richer `stats` details

**Files:** `backend.py`

- [ ] **Step 1:** For successful processing, include `priority`, `summary` (truncated if huge), and `raw_category` (optional) in each `details` item.
- [ ] **Step 2:** Ensure debug log entries also include summary/priority for parity (respect size limits).

---

## Phase 3 — LLM output validation

### Task 3.1: `validate_analysis` helper

**Files:** `backend.py` or new `analysis_schema.py`

- [ ] **Step 1:** After `json.loads` in providers (or once in backend after provider returns dict), validate:
  - `category` is non-empty string; normalize with existing `normalize_category`.
  - `priority` is int 1–5; coerce if string `"3"`; default to `3` or `1` on failure (document default).
  - `summary` is string; default to `""` if missing.
- [ ] **Step 2:** On validation failure, return `None` and set provider `last_error` / stats reason.
- [ ] **Step 3:** Add unit tests in `tests/test_analysis_validation.py` with good/bad payloads.

### Task 3.2: Provider-level parsing

**Files:** `llm_providers.py`

- [ ] **Step 1:** Optionally move JSON parse + strip fences into a shared `_parse_json_response(text) -> dict | None` to reduce duplication.
- [ ] **Step 2:** Groq: keep `response_format`; still validate keys in backend or shared validator.

---

## Phase 4 — Safety: delete rule and logging

### Task 4.1: Delete rule guard

**Files:** `backend.py`, `.env.example`, README

- [ ] **Step 1:** Before `mailbox.delete(uid)`, require `get_env_value("ALLOW_IMAP_DELETE") == "1"` (or similar) **or** `settings.allow_delete: true` in config (env is safer). If not allowed, log error, return rule failure, do not delete.
- [ ] **Step 2:** Document prominently in README.

### Task 4.2: `write_debug_log` concurrency

**Files:** `backend.py`, `requirements.txt`

- [ ] **Step 1:** Use `filelock.FileLock(DEBUG_LOG_PATH.with_suffix(".lock"))` around read-modify-write **or** POSIX-only `fcntl` if you want zero new deps (document Windows limitation if fcntl-only).
- [ ] **Step 2:** On lock timeout, log to stderr and skip write rather than corrupt JSON.

---

## Phase 5 — Provider and test script fixes

### Task 5.1: Gemini `thinking_level`

**Files:** `llm_providers.py`, `config.yaml` comment

- [ ] **Step 1:** Check current `google-generativeai` API for supported `GenerationConfig` fields; remove invalid `thinking_level` from dict passed to SDK if unsupported.
- [ ] **Step 2:** If unsupported, store `thinking_level` on provider for future use but do not pass to API until verified.

### Task 5.2: `test_connections.py`

**Files:** `test_connections.py`

- [ ] **Step 1:** Call `get_provider(provider_name, api_key, config)` with full `config` from `load_config()`.

### Task 5.3: `last_error` hygiene (optional)

**Files:** `llm_providers.py`

- [ ] **Step 1:** Change base class to instance-only: set `self.last_error = ""` in `__init__` of each concrete provider, or use a mixin. Low priority if single-threaded.

---

## Phase 6 — Documentation, repo hygiene, persistence story

### Task 6.1: README / CLAUDE accuracy

**Files:** `README.md`, `CLAUDE.md`

- [ ] **Step 1:** Remove or update SQLite / `database.py` claims: either “planned” or “debug_logs.json only” until DB exists.
- [ ] **Step 2:** Document `fetch_limit` as “first N unseen messages in server fetch order (typically oldest first).”
- [ ] **Step 3:** Document all new `settings` keys in one subsection.

### Task 6.2: `.gitignore` and sample config

**Files:** `.gitignore`, `config.yaml`

- [ ] **Step 1:** Add `emails.db`, `debug_logs.json`, `*.lock` if lock files sit next to logs.
- [ ] **Step 2:** Replace live email in committed `config.yaml` with `your.email@example.com` (user keeps real copy in private branch or local-only file — document pattern).

### Task 6.3: Optional minimal `database.py` (choose one)

**Files:** `database.py` (new), `backend.py`, README

- [ ] **Option A — Docs only:** Skip code; README states persistence is file-based logs for now.
- [ ] **Option B — Minimal audit log:** SQLite table `processed_messages(account_id, uid, subject_hash, category, priority, processed_at)` insert after successful rule application; **never delete rows** per project rules. Index by time. Wire one insert from `backend.py`.

---

## Phase 7 — Verification

### Task 7.1: Manual checks

- [ ] `dry_run: true` in YAML alone prevents IMAP mutations (with no CLI override).
- [ ] Failed `flag` does not mark message read and shows in `stats` as error.
- [ ] `Security: flag` leaves message unread but flagged (verify in client).
- [ ] Invalid LLM JSON increments errors/skips and does not mark read.
- [ ] `test_connections.py` runs against configured provider.

### Task 7.2: Automated tests

- [ ] Run `pytest tests/` if added; CI optional follow-up.

---

## Dependency graph (summary)

1. Phase 1 can start immediately.
2. Phase 2 depends on Phase 1 for `effective_dry_run` when testing.
3. Phase 3 can parallel Phase 2 if validators are merged carefully.
4. Phase 4 after Phase 2 (same files touch `backend.py`).
5. Phase 5 independent except Gemini fix touches same file as Phase 3 providers.
6. Phase 6 last (docs reflect final behavior).
7. Phase 7 always last.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Breaking users who relied on “all processed = read” | README migration + default rules use `mark_read` where appropriate |
| Delete guard blocks legitimate use | Document `ALLOW_IMAP_DELETE=1` |
| Lock file left on crash | Use context manager; optional stale lock cleanup in README |

---

*Created: 2026-04-18 — addresses full review thread (config, CLI, semantics, stats, validation, concurrency, providers, tests, docs, gitignore, optional DB).*
