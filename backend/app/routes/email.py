"""Email accounts and the "Waiting on you" list (Pro)."""
import imaplib
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import get_db
from ..services import license as license_svc
from ..services.mail import sync as mail

router = APIRouter(prefix="/api/email", tags=["email"])


class AccountBody(BaseModel):
    provider: str = Field(pattern="^(gmail|icloud|imap)$")
    address: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=4, max_length=200)
    host: str | None = Field(default=None, max_length=200)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=200)


class ThreadBody(BaseModel):
    status: str = Field(pattern="^(open|done|snoozed|dismissed)$")
    snooze_hours: int | None = Field(default=None, ge=1, le=24 * 30)


@router.get("/accounts")
def accounts():
    return {"accounts": mail.list_accounts()}


@router.post("/accounts")
def add_account(body: AccountBody):
    license_svc.require_pro("email")
    if body.provider == "imap" and not (body.host and body.port):
        raise HTTPException(status_code=422, detail="Server and port are required for other providers.")
    try:
        return mail.add_account(body.provider, body.address.strip(), body.password.replace(" ", "")
                                if body.provider == "gmail" else body.password,
                                body.host, body.port, body.username)
    except imaplib.IMAP4.error:
        raise HTTPException(status_code=400, detail="The email server didn't accept that address and app password.")
    except OSError:
        raise HTTPException(status_code=400, detail="Couldn't reach the email server. Check the server name and your connection.")


@router.delete("/accounts/{account_id}")
def remove_account(account_id: str):
    if not mail.remove_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"ok": True}


@router.post("/sync")
def sync_now():
    license_svc.require_pro("email")
    threading.Thread(target=mail.sync_all, daemon=True).start()
    return {"ok": True}


@router.get("/waiting")
def waiting():
    license_svc.require_pro("email")
    return {"threads": mail.waiting()}


@router.patch("/threads/{thread_id}")
def update_thread(thread_id: str, body: ThreadBody):
    until = None
    if body.status == "snoozed":
        until = (datetime.now(timezone.utc) + timedelta(hours=body.snooze_hours or 24)).isoformat()
    db = get_db()
    cur = db.execute("UPDATE email_threads SET status=?, snooze_until=? WHERE id=?", (body.status, until, thread_id))
    db.commit()
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


class ReplyBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


def _thread(thread_id: str):
    row = get_db().execute(
        "SELECT t.*, a.address, a.provider FROM email_threads t JOIN email_accounts a ON a.id=t.account_id "
        "WHERE t.id=?", (thread_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


@router.post("/google/connect")
def google_connect(request: Request):
    """Sign in with Google for Gmail — no app password."""
    license_svc.require_pro("email")
    from ..services.mail import gmail

    redirect_uri = f"http://127.0.0.1:{request.url.port}/oauth/google/callback"
    return {"auth_url": gmail.auth_url(redirect_uri)}


@router.post("/threads/{thread_id}/draft")
def draft_reply(thread_id: str):
    """A reply in the user's style, for them to review. Nothing is sent."""
    license_svc.require_pro("email")
    from ..services.mail import replies

    try:
        return {"text": replies.draft(_thread(thread_id))}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't write a draft right now. Try again in a moment.")


@router.post("/threads/{thread_id}/save-draft")
def save_draft(thread_id: str, body: ReplyBody):
    """Put the reviewed reply into Gmail Drafts, in the same conversation."""
    license_svc.require_pro("email")
    t = _thread(thread_id)
    if t["provider"] != "google":
        raise HTTPException(status_code=400, detail="Drafts go straight into Gmail only for Gmail sign-in accounts.")
    from ..services.mail import gmail

    gmail.create_draft({"id": t["account_id"], "address": t["address"]}, t, body.text)
    return {"ok": True}


@router.post("/threads/{thread_id}/send")
def send_reply(thread_id: str, body: ReplyBody):
    """The user pressed Send on a reply they reviewed."""
    license_svc.require_pro("email")
    t = _thread(thread_id)
    if t["provider"] != "google":
        raise HTTPException(status_code=400, detail="Sending from Jotva works with Gmail sign-in accounts.")
    from ..services.mail import gmail

    gmail.send_reply({"id": t["account_id"], "address": t["address"]}, t, body.text)
    db = get_db()
    db.execute("UPDATE email_threads SET status='done' WHERE id=?", (thread_id,))
    db.commit()
    return {"ok": True}


@router.get("/sent-for-you")
def sent_for_you():
    """Replies Jotva sent on the user's behalf (only when auto-send is on)."""
    rows = get_db().execute(
        "SELECT id, subject, counterpart_name, counterpart_email, reply_draft, replied_by_jotva_at FROM email_threads "
        "WHERE replied_by_jotva_at IS NOT NULL ORDER BY replied_by_jotva_at DESC LIMIT 50").fetchall()
    return {"threads": [dict(r) for r in rows]}
