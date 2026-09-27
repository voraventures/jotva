"""Email sync (Pro): keep a local copy of recent Inbox/Sent headers + excerpts,
work out which conversations are waiting on the user, and let the AI judge the
ones that might need a reply."""
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from ...db import get_db, new_id, now_iso
from ...events import hub
from ..keychain import delete_secret, get_secret, set_secret
from . import imap, parse, triage

log = logging.getLogger("jotva.mail")

POLL_SECONDS = 300
RETAIN_DAYS = 30
_sync_lock = threading.Lock()
_poller_started = False


def _password_key(account_id: str) -> str:
    return f"email_password:{account_id}"


def list_accounts() -> list[dict]:
    rows = get_db().execute("SELECT id, provider, address, last_sync, last_error FROM email_accounts ORDER BY created_at")
    return [dict(r) for r in rows]


def add_account(provider: str, address: str, password: str, host: str | None = None,
                port: int | None = None, username: str | None = None) -> dict:
    """Checks the login first; only a working account is saved. The app
    password goes to the macOS Keychain, never the database."""
    host, port = (host, port) if provider == "imap" else imap.PRESETS[provider]
    username = username or address
    conn = imap.connect(host, int(port), username, password)  # raises on bad login
    conn.logout()
    account_id = new_id()
    set_secret(_password_key(account_id), password)
    db = get_db()
    db.execute("INSERT INTO email_accounts(id,provider,address,host,port,username,created_at) VALUES(?,?,?,?,?,?,?)",
               (account_id, provider, address.lower(), host, int(port), username, now_iso()))
    db.commit()
    threading.Thread(target=sync_all, daemon=True).start()
    return {"id": account_id, "provider": provider, "address": address.lower()}


def remove_account(account_id: str) -> bool:
    db = get_db()
    cur = db.execute("DELETE FROM email_accounts WHERE id=?", (account_id,))
    db.execute("DELETE FROM email_messages WHERE account_id=?", (account_id,))
    db.execute("DELETE FROM email_threads WHERE account_id=?", (account_id,))
    db.commit()
    delete_secret(_password_key(account_id))
    return cur.rowcount > 0


def _save_messages(account: dict, parsed: list[dict]) -> set[str]:
    db = get_db()
    touched = set()
    for m in parsed:
        db.execute(
            "INSERT OR IGNORE INTO email_messages(id,account_id,thread_key,subject,from_email,from_name,"
            "to_emails,cc_emails,sent_at,snippet,is_from_me,is_bulk,message_id,provider_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"{account['id']}:{m['message_id']}", account["id"], m["thread_key"], m["subject"], m["from_email"],
             m["from_name"], json.dumps(m["to"]), json.dumps(m["cc"]), m["sent_at"], m["snippet"],
             int(m["is_from_me"]), int(m["is_bulk"]), m["message_id"], m.get("provider_id", "")))
        touched.add(m["thread_key"])
    db.commit()
    return touched


def rebuild_thread(account: dict, key: str) -> None:
    """Recompute one conversation from its messages. A new message resets the
    AI verdict (and reopens a thread the user had marked done)."""
    db = get_db()
    msgs = db.execute("SELECT * FROM email_messages WHERE account_id=? AND thread_key=? ORDER BY sent_at",
                      (account["id"], key)).fetchall()
    if not msgs:
        return
    last = msgs[-1]
    me = account["address"]
    other = next((m for m in reversed(msgs) if not m["is_from_me"]), last)
    thread_id = f"{account['id']}:{key}"
    existing = db.execute("SELECT last_message_id, status FROM email_threads WHERE id=?", (thread_id,)).fetchone()
    changed = not existing or existing["last_message_id"] != last["message_id"]
    values = dict(
        subject=last["subject"] or other["subject"], counterpart_name=other["from_name"],
        counterpart_email=other["from_email"], last_at=last["sent_at"], last_from_me=last["is_from_me"],
        last_message_id=last["message_id"], me_direct=int(me in json.loads(last["to_emails"])),
        is_bulk=int(any(m["is_bulk"] for m in msgs if not m["is_from_me"])))
    if not existing:
        db.execute("INSERT INTO email_threads(id,account_id,subject,counterpart_name,counterpart_email,last_at,"
                   "last_from_me,last_message_id,me_direct,is_bulk,provider_thread) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (thread_id, account["id"], *values.values(), key if account["provider"] == "google" else ""))
    elif changed:
        # A new message: a reply from the user settles it; a new one from them reopens it.
        status = "done" if values["last_from_me"] else "open"
        db.execute("UPDATE email_threads SET subject=?,counterpart_name=?,counterpart_email=?,last_at=?,last_from_me=?,"
                   "last_message_id=?,me_direct=?,is_bulk=?,needs_reply=NULL,triaged_at=NULL,notified=0,status=? WHERE id=?",
                   (*values.values(), status, thread_id))
    db.commit()


def sync_account(account: dict) -> None:
    if account["provider"] == "google":  # Gmail via Google sign-in
        from . import gmail

        state = json.loads(account["state"] or "{}")
        records = gmail.fetch_new(account, state)
        for key in _save_messages(account, records):
            rebuild_thread(account, key)
        db = get_db()
        db.execute("UPDATE email_accounts SET state=?, last_sync=?, last_error=NULL WHERE id=?",
                   (json.dumps(state), now_iso(), account["id"]))
        db.commit()
        return
    password = get_secret(_password_key(account["id"]))
    if not password:
        raise RuntimeError("Password missing from the Keychain; reconnect this account.")
    state = json.loads(account["state"] or "{}")
    conn = imap.connect(account["host"], account["port"], account["username"], password)
    try:
        raw = imap.fetch_new(conn, state, gmail=account["provider"] == "gmail")
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    mine = {account["address"]}
    parsed = [p for kind, data, thread in raw if (p := parse.parse(data, mine, thread))]
    for key in _save_messages(account, parsed):
        rebuild_thread(account, key)
    db = get_db()
    db.execute("UPDATE email_accounts SET state=?, last_sync=?, last_error=NULL WHERE id=?",
               (json.dumps(state), now_iso(), account["id"]))
    db.commit()


def _prune() -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETAIN_DAYS)).isoformat()
    db = get_db()
    db.execute("DELETE FROM email_messages WHERE sent_at < ?", (cutoff,))
    db.execute("DELETE FROM email_threads WHERE last_at < ?", (cutoff,))
    db.commit()


def sync_all() -> None:
    from .. import license

    if not license.has_feature("email") or not _sync_lock.acquire(blocking=False):
        return
    try:
        for row in get_db().execute("SELECT * FROM email_accounts").fetchall():
            account = dict(row)
            try:
                sync_account(account)
            except Exception as exc:
                log.warning("Email sync failed for %s: %s", account["provider"], exc)
                db = get_db()
                db.execute("UPDATE email_accounts SET last_error=? WHERE id=?", (str(exc)[:200], account["id"]))
                db.commit()
        _prune()
        new_urgent = triage.run()
        from . import replies

        auto_sent = replies.autosend_pass()  # opt-in only; a no-op by default
        hub.emit("email_updated", {"waiting": len(waiting()), "auto_sent": len(auto_sent)})
        if new_urgent:
            hub.emit("email_urgent", {"count": len(new_urgent), "first": new_urgent[0]})
    finally:
        _sync_lock.release()


def waiting() -> list[dict]:
    """Conversations waiting on the user, most urgent and oldest first."""
    now = now_iso()
    rows = get_db().execute(
        "SELECT t.*, a.address AS account, a.provider AS provider FROM email_threads t JOIN email_accounts a ON a.id = t.account_id "
        "WHERE t.needs_reply=1 AND t.last_from_me=0 AND (t.status='open' OR (t.status='snoozed' AND t.snooze_until <= ?)) "
        "ORDER BY CASE t.urgency WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, t.last_at", (now,)).fetchall()
    return [{**dict(r), "tasks": json.loads(r["tasks"] or "[]")} for r in rows]


def start_poller() -> None:
    global _poller_started
    if _poller_started:
        return
    _poller_started = True

    def loop():
        while True:
            try:
                if get_db().execute("SELECT 1 FROM email_accounts LIMIT 1").fetchone():
                    sync_all()
            except Exception:
                log.exception("Email poller pass failed")
            time.sleep(POLL_SECONDS)

    threading.Thread(target=loop, daemon=True, name="email-poller").start()
