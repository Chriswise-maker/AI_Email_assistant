"""
Flask API server for the Email Triage Assistant.

Wraps the existing backend (backend.py, database.py) as REST endpoints
and serves the single-page frontend from templates/index.html.

Run with:  python3 server.py
Opens at:  http://localhost:5001
"""

import re
import threading
from datetime import datetime

from flask import Flask, jsonify, request, render_template

from database import (
    get_latest_run, get_emails_for_run, get_all_runs,
    search_emails, get_stats, get_email_by_id, delete_email,
)
from backend import process_emails, get_reply_draft, delete_email_from_imap
from utils import load_config, save_config, set_account_password

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sender(sender_str: str) -> tuple[str, str]:
    """Parse 'Display Name <email>' or bare email into (name, email)."""
    if not sender_str:
        return ("Unknown", "")
    m = re.match(r'^(.+?)\s*<(.+?)>\s*$', sender_str)
    if m:
        return (m.group(1).strip().strip('"'), m.group(2))
    if "@" in sender_str:
        local = sender_str.split("@")[0].replace(".", " ").title()
        return (local, sender_str)
    return (sender_str, "")


def _fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except Exception:
        return ""


def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %-d")
    except Exception:
        return ""


def _classify(email: dict) -> tuple[str, str | None]:
    """Return (section, css_priority_class) based on priority."""
    p = email.get("priority", 1)
    if p >= 4:
        return "attention", "p1"
    if p == 3:
        return "noted", "p2"
    return "quiet", None


_WARM_TAGS = {"Security"}


def _format_email(e: dict) -> dict:
    """Turn a DB email row into the shape the frontend expects."""
    sender_name, sender_email = _parse_sender(e.get("sender", ""))
    _, pclass = _classify(e)
    # Prefer the original email date over processing time
    email_date_str = e.get("email_date") or e.get("processed_at") or ""
    return {
        "id": e.get("id"),
        "priority": pclass,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "sender_raw": e.get("sender", ""),
        "time": _fmt_time(email_date_str),
        "date": _fmt_date(email_date_str),
        "subject": e.get("subject", ""),
        "summary": e.get("summary", ""),
        "category": e.get("category", "Other"),
        "tag_warm": e.get("category") in _WARM_TAGS,
        "action_applied": e.get("action", ""),
        "account": e.get("account", ""),
    }


def _compute_timing(emails: list[dict]) -> tuple[int, float]:
    """Estimate total seconds and avg seconds/email from processed_at stamps."""
    ts = []
    for e in emails:
        try:
            ts.append(datetime.fromisoformat(e["processed_at"]))
        except Exception:
            pass
    if len(ts) < 2:
        return 0, 0.0
    ts.sort()
    total = (ts[-1] - ts[0]).total_seconds()
    return round(total), round(total / len(ts), 1)


# ---------------------------------------------------------------------------
# Triage runner (async so the UI doesn't block)
# ---------------------------------------------------------------------------

_triage = {"running": False, "result": None}


def _run_triage(dry_run: bool) -> None:
    _triage["running"] = True
    _triage["result"] = None
    try:
        _triage["result"] = process_emails(dry_run=dry_run)
    finally:
        _triage["running"] = False


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/briefing")
def api_briefing():
    run = get_latest_run()
    if not run:
        return jsonify({"run": None, "stats": {}, "attention": [], "noted": [], "quiet": []})

    emails = get_emails_for_run(run["run_id"])

    attention, noted, quiet = [], [], []
    for e in emails:
        section, _ = _classify(e)
        fe = _format_email(e)
        {"attention": attention, "noted": noted, "quiet": quiet}[section].append(fe)

    total_sec, avg_sec = _compute_timing(emails)
    total = run.get("total_processed", 0)

    # Human-readable run date
    run_date = ""
    if run.get("started_at"):
        try:
            dt = datetime.fromisoformat(run["started_at"])
            part = "Morning" if dt.hour < 12 else "Evening"
            run_date = dt.strftime(f"%A, %B %-d") + f" \u00b7 {part}"
        except Exception:
            pass

    config = load_config()
    accounts = [a["id"] for a in config.get("accounts", []) if a.get("enabled")]

    return jsonify({
        "run": {
            "run_id": run["run_id"],
            "date": run_date,
            "model": run.get("model", ""),
            "provider": run.get("provider", ""),
        },
        "stats": {
            "processed": total,
            "urgent": len(attention),
            "action_needed": len(noted),
            "avg_seconds": avg_sec,
            "total_seconds": total_sec,
            "accounts": accounts,
            "model": run.get("model", ""),
        },
        "attention": attention,
        "noted": noted,
        "quiet": quiet,
    })


@app.route("/api/archive")
def api_archive():
    runs = get_all_runs(limit=50)
    out = []
    for r in runs:
        dt_str, part = "", ""
        if r.get("started_at"):
            try:
                dt = datetime.fromisoformat(r["started_at"])
                dt_str = dt.strftime("%b %-d")
                part = "Morning" if dt.hour < 12 else "Evening"
            except Exception:
                pass
        processed = r.get("total_processed", 0)
        errors = r.get("total_errors", 0)
        urgent_label = f"{errors} errors" if errors else "0 urgent"
        out.append({
            "run_id": r["run_id"],
            "date": dt_str,
            "label": f"{part} Briefing",
            "stats": f"{processed} \u00b7 {urgent_label}",
            "model": r.get("model", ""),
        })
    return jsonify(out)


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    category = request.args.get("category", "")
    account = request.args.get("account", "")
    results = search_emails(query=q, category=category, account=account, limit=100)
    out = []
    for e in results:
        fe = _format_email(e)
        fe["date"] = _fmt_date(e.get("processed_at", ""))
        out.append(fe)
    return jsonify(out)


@app.route("/api/triage", methods=["POST"])
def api_triage():
    if _triage["running"]:
        return jsonify({"status": "already_running"}), 409
    dry_run = (request.json or {}).get("dry_run", False)
    thread = threading.Thread(target=_run_triage, args=(dry_run,), daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/triage/status")
def api_triage_status():
    return jsonify({
        "running": _triage["running"],
        "result": _triage["result"],
    })


@app.route("/api/settings")
def api_settings():
    config = load_config()
    provider_name = config.get("settings", {}).get("provider", "groq")
    model = config.get("providers", {}).get(provider_name, {}).get("model", "")
    return jsonify({
        "accounts": [
            {"id": a["id"], "email": a.get("email", ""), "enabled": a.get("enabled", True)}
            for a in config.get("accounts", [])
        ],
        "provider": provider_name,
        "model": model,
        "fetch_limit": config.get("settings", {}).get("fetch_limit", 50),
        "dry_run": config.get("settings", {}).get("dry_run", False),
    })


@app.route("/api/accounts", methods=["POST"])
def api_add_account():
    body = request.json or {}
    acc_id = (body.get("id") or "").strip()
    email = (body.get("email") or "").strip()
    server = (body.get("server") or "").strip()
    password = (body.get("password") or "").strip()

    if not all([acc_id, email, server, password]):
        return jsonify({"error": "All fields are required"}), 400

    config = load_config()
    # Check for duplicate ID
    for a in config.get("accounts", []):
        if a["id"].lower() == acc_id.lower():
            return jsonify({"error": f"Account '{acc_id}' already exists"}), 409

    new_account = {
        "id": acc_id,
        "email": email,
        "server": server,
        "enabled": True,
        "provider": "imap",
    }
    config.setdefault("accounts", []).append(new_account)
    save_config(config)
    set_account_password(acc_id, password)

    return jsonify({"id": acc_id, "email": email, "enabled": True})


@app.route("/api/settings/toggle-account/<account_id>", methods=["POST"])
def api_toggle_account(account_id):
    config = load_config()
    for a in config.get("accounts", []):
        if a["id"] == account_id:
            a["enabled"] = not a.get("enabled", True)
            save_config(config)
            return jsonify({"id": account_id, "enabled": a["enabled"]})
    return jsonify({"error": "Account not found"}), 404


# Available models per provider — extend as needed
_PROVIDER_MODELS = {
    "claude": [
        {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 — fastest, cheapest"},
        {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6 — balanced"},
        {"id": "claude-opus-4-6", "label": "Claude Opus 4.6 — most capable"},
    ],
    "groq": [
        {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B Versatile"},
        {"id": "llama-3.1-8b-instant", "label": "Llama 3.1 8B Instant — fastest"},
    ],
    "gemini": [
        {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
        {"id": "gemini-2.5-pro-preview-03-25", "label": "Gemini 2.5 Pro Preview"},
    ],
    "deepseek": [
        {"id": "deepseek-chat", "label": "DeepSeek Chat"},
        {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner"},
    ],
}


@app.route("/api/settings/models")
def api_settings_models():
    config = load_config()
    # Allow querying models for a specific provider (for live preview)
    provider_name = request.args.get("provider") or config.get("settings", {}).get("provider", "groq")
    current_model = config.get("providers", {}).get(provider_name, {}).get("model", "")
    models = _PROVIDER_MODELS.get(provider_name, [])
    return jsonify({"provider": provider_name, "current": current_model, "models": models})


@app.route("/api/settings/model", methods=["POST"])
def api_set_model():
    body = request.json or {}
    model_id = body.get("model", "").strip()
    if not model_id:
        return jsonify({"error": "model required"}), 400
    config = load_config()
    provider_name = config.get("settings", {}).get("provider", "groq")
    if "providers" not in config:
        config["providers"] = {}
    if provider_name not in config["providers"]:
        config["providers"][provider_name] = {}
    config["providers"][provider_name]["model"] = model_id
    save_config(config)
    return jsonify({"provider": provider_name, "model": model_id})


@app.route("/api/settings/provider", methods=["POST"])
def api_set_provider():
    body = request.json or {}
    new_provider = (body.get("provider") or "").strip().lower()
    if new_provider not in _PROVIDER_MODELS:
        return jsonify({"error": f"Unknown provider: {new_provider}"}), 400
    config = load_config()
    config.setdefault("settings", {})["provider"] = new_provider
    save_config(config)
    # Return the new provider's current model + available models
    current_model = config.get("providers", {}).get(new_provider, {}).get("model", "")
    models = _PROVIDER_MODELS.get(new_provider, [])
    return jsonify({"provider": new_provider, "model": current_model, "models": models})


@app.route("/api/settings/dry-run", methods=["POST"])
def api_toggle_dry_run():
    config = load_config()
    current = config.get("settings", {}).get("dry_run", False)
    config.setdefault("settings", {})["dry_run"] = not current
    save_config(config)
    return jsonify({"dry_run": not current})


@app.route("/api/settings/fetch-limit", methods=["POST"])
def api_set_fetch_limit():
    body = request.json or {}
    try:
        limit = int(body.get("fetch_limit", 50))
        limit = max(1, min(limit, 500))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid fetch_limit"}), 400
    config = load_config()
    config.setdefault("settings", {})["fetch_limit"] = limit
    save_config(config)
    return jsonify({"fetch_limit": limit})


# ---------------------------------------------------------------------------
# Draft Reply & Delete
# ---------------------------------------------------------------------------

@app.route("/api/draft-reply", methods=["POST"])
def api_draft_reply():
    body = request.json or {}
    email_id = body.get("email_id")
    instruction = (body.get("instruction") or "").strip()
    if not instruction:
        return jsonify({"error": "instruction required"}), 400

    # Build email_data from the stored record or from the payload
    email_data = {}
    if email_id:
        row = get_email_by_id(email_id)
        if row:
            email_data = row
    # Allow caller to pass fields directly (fallback)
    for key in ("sender", "subject", "summary", "category"):
        if key not in email_data and key in body:
            email_data[key] = body[key]

    config = load_config()
    draft = get_reply_draft(email_data, instruction, config)
    if draft is None:
        return jsonify({"error": "Draft generation failed — check provider API key"}), 500
    return jsonify({"draft": draft})


@app.route("/api/delete/<int:email_id>", methods=["DELETE"])
def api_delete_email(email_id):
    row = get_email_by_id(email_id)
    if not row:
        return jsonify({"error": "Email not found"}), 404

    imap_msg = ""
    uid = row.get("uid")
    account_id = row.get("account")
    if uid and account_id:
        config = load_config()
        ok, err = delete_email_from_imap(account_id, uid, config)
        if not ok:
            imap_msg = err

    delete_email(email_id)
    return jsonify({"ok": True, "imap_warning": imap_msg})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Email Triage UI → http://localhost:5001")
    app.run(debug=True, port=5001)
