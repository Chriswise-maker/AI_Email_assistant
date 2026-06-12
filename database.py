"""
Email History Database (SQLite)

Stores every processed email for persistent history, search, and filtering.
The DB file lives in the project root as emails.db — no external server needed.
"""

import sqlite3
import datetime
import uuid
from pathlib import Path
from typing import Optional

from utils import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "emails.db"


def _get_connection() -> sqlite3.Connection:
    """Get a connection with row_factory set for dict-like access."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read performance
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT,
            account TEXT NOT NULL,
            sender TEXT,
            subject TEXT,
            category TEXT,
            priority INTEGER DEFAULT 1,
            summary TEXT,
            action TEXT,
            run_id TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            email_date TEXT,
            dry_run INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS triage_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            total_processed INTEGER DEFAULT 0,
            total_errors INTEGER DEFAULT 0,
            total_skipped INTEGER DEFAULT 0,
            provider TEXT,
            model TEXT
        )
    """)
    # Migrate existing DBs: add email_date column if missing
    cursor = conn.execute("PRAGMA table_info(emails)")
    columns = {row[1] for row in cursor.fetchall()}
    if "email_date" not in columns:
        conn.execute("ALTER TABLE emails ADD COLUMN email_date TEXT")

    # Deduplicate: unique constraint on (uid, account) so re-processing
    # the same email doesn't create duplicate rows.
    # Clean up pre-existing duplicates first (keep the newest row per uid+account).
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_emails_uid_account ON emails(uid, account)")
    except sqlite3.IntegrityError:
        conn.execute("""
            DELETE FROM emails WHERE id NOT IN (
                SELECT MAX(id) FROM emails GROUP BY uid, account
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_emails_uid_account ON emails(uid, account)")

    # Indexes for common queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_run_id ON emails(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_priority ON emails(priority)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_account ON emails(account)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_processed_at ON emails(processed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_email_date ON emails(email_date)")
    conn.commit()
    conn.close()


def create_run(provider: str = "", model: str = "") -> str:
    """Start a new triage run. Returns the run_id."""
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    conn = _get_connection()
    conn.execute(
        "INSERT INTO triage_runs (run_id, started_at, provider, model) VALUES (?, ?, ?, ?)",
        (run_id, datetime.datetime.now().isoformat(), provider, model),
    )
    conn.commit()
    conn.close()
    return run_id


def finish_run(run_id: str, processed: int, errors: int, skipped: int) -> None:
    """Update run stats after completion."""
    conn = _get_connection()
    conn.execute(
        "UPDATE triage_runs SET total_processed=?, total_errors=?, total_skipped=? WHERE run_id=?",
        (processed, errors, skipped, run_id),
    )
    conn.commit()
    conn.close()


def save_email(
    run_id: str,
    uid: str,
    account: str,
    sender: str,
    subject: str,
    category: str,
    priority: int,
    summary: str,
    action: str,
    dry_run: bool = False,
    email_date: str = "",
) -> None:
    """Save a single processed email to the database."""
    conn = _get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO emails
           (uid, account, sender, subject, category, priority, summary, action, run_id, processed_at, email_date, dry_run)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, account, sender, subject, category, priority, summary, action, run_id,
         datetime.datetime.now().isoformat(), email_date, 1 if dry_run else 0),
    )
    conn.commit()
    conn.close()


def get_latest_run() -> Optional[dict]:
    """Get the most recent triage run."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM triage_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_emails_for_run(run_id: str) -> list[dict]:
    """Get all emails from a specific triage run."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM emails WHERE run_id = ? ORDER BY priority DESC, COALESCE(email_date, processed_at) DESC, category",
        (run_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_runs(limit: int = 50) -> list[dict]:
    """Get recent triage runs, newest first."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM triage_runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_emails(
    query: str = "",
    category: str = "",
    account: str = "",
    priority_min: int = 0,
    date_from: str = "",
    date_to: str = "",
    limit: int = 200,
) -> list[dict]:
    """Search email history with filters."""
    conditions = []
    params = []

    if query:
        conditions.append("(subject LIKE ? OR sender LIKE ? OR summary LIKE ?)")
        q = f"%{query}%"
        params.extend([q, q, q])
    if category:
        conditions.append("category = ?")
        params.append(category)
    if account:
        conditions.append("account = ?")
        params.append(account)
    if priority_min > 0:
        conditions.append("priority >= ?")
        params.append(priority_min)
    if date_from:
        conditions.append("processed_at >= ?")
        params.append(date_from)
    if date_to:
        # Add end-of-day to include the full day
        conditions.append("processed_at <= ?")
        params.append(date_to + "T23:59:59")

    where = " AND ".join(conditions) if conditions else "1=1"
    params.append(limit)

    conn = _get_connection()
    rows = conn.execute(
        f"SELECT * FROM emails WHERE {where} ORDER BY COALESCE(email_date, processed_at) DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_email_by_id(email_id: int) -> Optional[dict]:
    """Get a single email by its database ID."""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_email(email_id: int) -> None:
    """Remove an email record from the database."""
    conn = _get_connection()
    conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Get summary statistics for the sidebar/dashboard."""
    conn = _get_connection()
    total = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    runs = conn.execute("SELECT COUNT(*) FROM triage_runs").fetchone()[0]
    by_category = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM emails GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    by_priority = conn.execute(
        "SELECT priority, COUNT(*) as cnt FROM emails GROUP BY priority ORDER BY priority DESC"
    ).fetchall()
    accounts = conn.execute(
        "SELECT DISTINCT account FROM emails"
    ).fetchall()
    conn.close()

    return {
        "total_emails": total,
        "total_runs": runs,
        "by_category": {r["category"]: r["cnt"] for r in by_category},
        "by_priority": {r["priority"]: r["cnt"] for r in by_priority},
        "accounts": [r["account"] for r in accounts],
    }


# Auto-initialize on import
init_db()
