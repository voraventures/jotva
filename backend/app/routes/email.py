"""Email accounts and the "Waiting on you" list (Pro)."""
import imaplib
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
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
