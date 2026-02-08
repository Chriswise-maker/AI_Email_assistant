# Phase 4 Implementation Plan: Optimization & Polish

## Architecture Refinement
Currently, `fetch_emails` opens/closes the IMAP connection, meaning `apply_rules` cannot easily perform actions (mark read, move, flag) without re-opening connections.

We will refactor `process_emails` in `backend.py` to:
1.  Open the `MailBox` connection.
2.  Fetch emails (using the open mailbox).
3.  Analyze each email.
4.  Perform actions (using the open mailbox and email UID).
5.  Generate the daily briefing.

## Changes

### 1. `config.yaml`
- Add `fetch_limit: 50` to settings.

### 2. `backend.py`
- **Refactor `fetch_emails`**: Acceptance of an active `mailbox` object instead of creating a new one.
- **Update `process_emails`**: Use `with MailBox(...)` at the top level.
- **Implement `apply_rules`**: Use `mailbox.flag`, `mailbox.move`, etc. using email UIDs.
- **Implement `append_to_briefing`**: 
    - Aggregate summaries by category.
    - Write to `daily_briefing.md` with a timestamp header.

## Verification
- Run Triage in Dry Run mode first.
- Run Live Triage and check if emails are marked as read (as per user screenshot rules).
- Check `daily_briefing.md` content.
