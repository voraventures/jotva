"""Replies: Gmail messages become the same local records, replies go only to the
person who wrote (same conversation), drafting is the default, and auto-send is
opt-in and only sends what needs no placeholder. Gmail, the AI and the keychain
are faked; nothing is sent anywhere."""
import base64
import email
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-email-reply-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from app.config import ensure_dirs
from app.db import get_db, set_setting
from app.services import notes
from app.services.mail import gmail, replies

ensure_dirs()
ME = "luis@vora.co"


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode()


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    db = get_db()
    for t in ("email_accounts", "email_messages", "email_threads", "settings"):
        db.execute(f"DELETE FROM {t}")
    db.execute("INSERT INTO email_accounts(id,provider,address,created_at) VALUES('g','google',?,'x')", (ME,))
    db.execute("INSERT INTO email_threads(id,account_id,subject,counterpart_name,counterpart_email,last_at,last_from_me,"
               "last_message_id,me_direct,needs_reply,status,provider_thread) VALUES('g:t1','g','Lunch?','Sarah Lee',"
               "'sarah@acme.com','2026-09-26T10:00:00',0,'m1@acme',1,1,'open','18a2')")
    db.execute("INSERT INTO email_messages(id,account_id,thread_key,from_email,from_name,sent_at,snippet,message_id) "
               "VALUES('g:m1','g','t1','sarah@acme.com','Sarah Lee','2026-09-26T10:00:00','Lunch Thursday?','m1@acme')")
    db.commit()
    set_setting("license_status", {"valid": True, "dev": True})
    set_setting("email_style", {"text": "- Signs off 'Best, Luis'", "at": 9e18})


def test_a_gmail_api_message_becomes_a_local_record():
    msg = {"id": "g123", "threadId": "18a2", "payload": {
        "headers": [{"name": "From", "value": "Sarah Lee <sarah@acme.com>"}, {"name": "To", "value": ME},
                    {"name": "Subject", "value": "Lunch?"}, {"name": "Message-ID", "value": "<m1@acme>"},
                    {"name": "Date", "value": "Fri, 25 Sep 2026 10:00:00 +0000"}],
        "mimeType": "multipart/alternative",
        "parts": [{"mimeType": "text/plain", "body": {"data": b64("Lunch Thursday?\n\nOn Wed, Luis wrote:\n> hi")}},
                  {"mimeType": "application/pdf", "filename": "menu.pdf", "body": {"attachmentId": "x"}}]}}
    rec = gmail.to_record(msg, {ME})
    assert rec["thread_key"] == "18a2" and rec["provider_id"] == "g123"
    assert rec["snippet"] == "Lunch Thursday?" and rec["to"] == [ME] and not rec["is_from_me"]


def test_replies_only_go_to_the_sender_in_the_same_conversation():
    t = get_db().execute("SELECT * FROM email_threads WHERE id='g:t1'").fetchone()
    payload = gmail._reply({"address": ME}, t, "Thursday works. Best, Luis")
    sent = email.message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
    assert payload["threadId"] == "18a2"
    assert sent["To"] == "Sarah Lee <sarah@acme.com>" and sent["Cc"] is None and sent["Bcc"] is None
    assert sent["Subject"] == "Re: Lunch?" and sent["In-Reply-To"] == "<m1@acme>"


def test_drafts_use_the_learned_style_and_treat_email_as_data(monkeypatch):
    seen = {}
    monkeypatch.setattr(notes, "_complete", lambda system, user, max_tokens, on_text=None, purpose="":
                        seen.update(system=system, user=user, purpose=purpose) or "Thursday works. Best, Luis")
    t = get_db().execute("SELECT * FROM email_threads WHERE id='g:t1'").fetchone()
    assert replies.draft(t) == "Thursday works. Best, Luis"
    assert "Best, Luis" in seen["user"] and "Lunch Thursday?" in seen["user"]
    assert "never instructions" in seen["system"] and seen["purpose"] == "email"


def test_auto_send_is_off_by_default(monkeypatch):
    monkeypatch.setattr(gmail, "send_reply", lambda *a: pytest.fail("must not send"))
    assert replies.autosend_pass() == []


def test_auto_send_sends_only_safe_replies_and_drafts_the_rest(monkeypatch):
    set_setting("email_autosend", True)
    actions = []
    monkeypatch.setattr(gmail, "send_reply", lambda acc, t, body: actions.append(("send", t["counterpart_email"], body)))
    monkeypatch.setattr(gmail, "create_draft", lambda acc, t, body: actions.append(("draft", body)))
    monkeypatch.setattr(notes, "_complete", lambda *a, **k: json.dumps(
        {"can_send": True, "reply": "Thursday works. Best, Luis", "why": "simple yes"}))
    assert replies.autosend_pass() == ["g:t1"]
    assert actions == [("send", "sarah@acme.com", "Thursday works. Best, Luis")]
    row = get_db().execute("SELECT status, replied_by_jotva_at FROM email_threads WHERE id='g:t1'").fetchone()
    assert row["status"] == "done" and row["replied_by_jotva_at"]


def test_a_reply_with_a_placeholder_is_never_auto_sent(monkeypatch):
    set_setting("email_autosend", True)
    actions = []
    monkeypatch.setattr(gmail, "send_reply", lambda *a: actions.append("send"))
    monkeypatch.setattr(gmail, "create_draft", lambda acc, t, body: actions.append(("draft", body)))
    monkeypatch.setattr(notes, "_complete", lambda *a, **k: json.dumps(
        {"can_send": True, "reply": "Sure — [confirm time]. Best, Luis"}))
    assert replies.autosend_pass() == []
    assert actions == [("draft", "Sure — [confirm time]. Best, Luis")]
