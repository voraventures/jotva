"""Gmail through Google sign-in (no app password): read recent Inbox + Sent,
create reply drafts, and — only when the user turns it on — send replies.

Scopes: gmail.readonly (read) and gmail.compose (drafts and sending). Until
Google verifies Jotva for these restricted scopes, sign-in works for the test
users listed on the Google Cloud consent screen."""
import base64
import json
import time
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

import httpx

from ...db import get_db, new_id, now_iso
from ..calendars import google_cal
from ..keychain import get_secret, set_secret
from . import parse

SCOPES = ("openid email https://www.googleapis.com/auth/gmail.readonly "
          "https://www.googleapis.com/auth/gmail.compose")
API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_PER_SYNC = 300


def _key(account_id: str) -> str:
    return f"email_password:{account_id}"  # holds the OAuth token set (JSON) for Gmail accounts


def auth_url(redirect_uri: str) -> str:
    return google_cal.build_auth_url(redirect_uri, scopes=SCOPES, purpose="gmail")


def finish_connect(tokens: dict) -> dict:
    granted = set((tokens.get("scope") or "").split())
    if "https://www.googleapis.com/auth/gmail.readonly" not in granted:
        raise RuntimeError("Gmail access wasn't granted")
    profile = httpx.get(f"{API}/profile", headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=15)
    profile.raise_for_status()
    address = profile.json()["emailAddress"].lower()
    db = get_db()
    existing = db.execute("SELECT id FROM email_accounts WHERE provider='google' AND address=?", (address,)).fetchone()
    account_id = existing["id"] if existing else new_id()
    set_secret(_key(account_id), json.dumps(tokens))
    if not existing:
        db.execute("INSERT INTO email_accounts(id,provider,address,created_at) VALUES(?,?,?,?)",
                   (account_id, "google", address, now_iso()))
        db.commit()
    import threading
    from . import sync

    threading.Thread(target=sync.sync_all, daemon=True).start()
    return {"id": account_id, "provider": "google", "address": address}


def _token(account_id: str) -> str:
    raw = get_secret(_key(account_id))
    if not raw:
        raise RuntimeError("Gmail sign-in missing; reconnect Gmail in Settings.")
    tokens = google_cal.refresh_tokens(json.loads(raw))
    if not tokens:
        raise RuntimeError("Gmail sign-in expired; reconnect Gmail in Settings.")
    set_secret(_key(account_id), json.dumps(tokens))
    return tokens["access_token"]


def _get(token: str, path: str, **params) -> dict:
    resp = httpx.get(f"{API}/{path}", headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _text(payload: dict) -> tuple[str, str]:
    """(plain, html) text of a Gmail message payload; attachments are skipped."""
    plain = html = ""
    stack = [payload]
    while stack:
        part = stack.pop(0)
        stack.extend(part.get("parts") or [])
        data = (part.get("body") or {}).get("data")
        if not data or part.get("filename"):
            continue
        text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
        if part.get("mimeType") == "text/plain" and not plain:
            plain = text
        elif part.get("mimeType") == "text/html" and not html:
            html = text
    return plain, html


def to_record(msg: dict, mine: set[str]) -> dict | None:
    """A Gmail API message (format=full) as the same record parse.parse builds."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    email = EmailMessage()
    for name in ("from", "to", "cc", "subject", "date", "message-id", "references", "in-reply-to",
                 "list-unsubscribe", "list-id", "precedence", "auto-submitted"):
        if name in headers:
            try:
                email[name] = headers[name]
            except Exception:
                pass
    plain, html = _text(msg.get("payload", {}))
    if plain:
        email.set_content(plain)
    elif html:
        email.set_content(html, subtype="html")
    record = parse.parse(bytes(email), mine, provider_thread=msg.get("threadId"))
    if record:
        record["provider_id"] = msg["id"]
    return record


def fetch_new(account: dict, state: dict) -> list[dict]:
    token = _token(account["id"])
    since = int(state.get("after") or (time.time() - 14 * 86400))
    query = f"after:{since - 3600} (in:inbox OR in:sent)"
    ids, page = [], None
    while len(ids) < MAX_PER_SYNC:
        data = _get(token, "messages", q=query, maxResults=100, **({"pageToken": page} if page else {}))
        ids += [m["id"] for m in data.get("messages", [])]
        page = data.get("nextPageToken")
        if not page:
            break
    db = get_db()
    known = {r["provider_id"] for r in db.execute(
        "SELECT provider_id FROM email_messages WHERE account_id=? AND provider_id != ''", (account["id"],))}
    records = []
    for gid in ids:
        if gid in known:
            continue
        rec = to_record(_get(token, f"messages/{gid}", format="full"), {account["address"]})
        if rec:
            records.append(rec)
    state["after"] = int(time.time())
    return records


def _reply(account: dict, thread: dict, body: str) -> dict:
    """RFC 822 reply to the other person only, in the same Gmail conversation."""
    msg = EmailMessage()
    msg["From"] = account["address"]
    msg["To"] = formataddr((thread["counterpart_name"], thread["counterpart_email"]))
    subject = thread["subject"] or ""
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if thread["last_message_id"]:
        msg["In-Reply-To"] = f"<{thread['last_message_id']}>"
        msg["References"] = f"<{thread['last_message_id']}>"
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(bytes(msg)).decode()
    return {"raw": raw, "threadId": thread["provider_thread"] or None}


def create_draft(account: dict, thread: dict, body: str) -> str:
    token = _token(account["id"])
    resp = httpx.post(f"{API}/drafts", headers={"Authorization": f"Bearer {token}"},
                      json={"message": _reply(account, thread, body)}, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


def send_reply(account: dict, thread: dict, body: str) -> str:
    """Only ever to the person who wrote, in the same conversation (the guardrail
    for replies Jotva sends on the user's behalf)."""
    if not parseaddr(thread["counterpart_email"])[1] or thread["counterpart_email"] == account["address"]:
        raise RuntimeError("No one to reply to in this conversation")
    token = _token(account["id"])
    resp = httpx.post(f"{API}/messages/send", headers={"Authorization": f"Bearer {token}"},
                      json=_reply(account, thread, body), timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]
