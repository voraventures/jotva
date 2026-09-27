"""Email "Waiting on you" (Pro): parsing, bulk detection, conversation state,
AI triage and the API. Sample emails, a fake IMAP login and a fake AI — no real
mailbox, keychain or network is touched."""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-email-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import ensure_dirs
from app.db import get_db, set_setting
from app.routes import email as email_routes
from app.services import license, notes
from app.services.mail import imap, parse, sync, triage

ensure_dirs()
app = FastAPI()
app.include_router(email_routes.router)
client = TestClient(app)
ME = "luis@vora.co"


def raw(frm, to, subject, body, msg_id, refs="", extra=""):
    return (f"From: {frm}\r\nTo: {to}\r\nSubject: {subject}\r\nDate: Fri, 25 Sep 2026 10:00:00 +0000\r\n"
            f"Message-ID: <{msg_id}>\r\n{('References: <' + refs + '>' + chr(13) + chr(10)) if refs else ''}{extra}"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n").encode()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    db = get_db()
    for t in ("email_accounts", "email_messages", "email_threads", "settings"):
        db.execute(f"DELETE FROM {t}")
    db.commit()
    set_setting("license_status", {"valid": True, "dev": True})
    secrets = {}
    monkeypatch.setattr(sync, "set_secret", lambda k, v: secrets.__setitem__(k, v))
    monkeypatch.setattr(sync, "get_secret", lambda k: secrets.get(k))
    monkeypatch.setattr(sync, "delete_secret", lambda k: secrets.pop(k, None))
    monkeypatch.setattr(sync.threading, "Thread", lambda **kw: NS(start=lambda: None))
    return secrets


def account():
    db = get_db()
    db.execute("INSERT INTO email_accounts(id,provider,address,host,port,username,created_at) "
               "VALUES('acc','gmail',?,'imap.gmail.com',993,?,'2026-09-27')", (ME, ME))
    db.commit()
    return dict(db.execute("SELECT * FROM email_accounts WHERE id='acc'").fetchone())


def test_parse_keeps_only_the_new_text_and_threads_replies():
    body = "Can you approve the Q4 budget by Tuesday?\n\nOn Thu, Sarah wrote:\n> old stuff"
    m = parse.parse(raw("Sarah Lee <sarah@acme.com>", ME, "Q4 budget", body, "b2@acme", refs="b1@acme"), {ME})
    assert m["snippet"] == "Can you approve the Q4 budget by Tuesday?"
    assert m["thread_key"] == "b1@acme" and m["from_name"] == "Sarah Lee" and not m["is_bulk"]


def test_newsletters_and_notifications_are_bulk():
    news = raw("Weekly <news@brand.com>", ME, "Deals", "Hi", "n1@b", extra="List-Unsubscribe: <mailto:x@b>\r\n")
    bot = raw("GitHub <notifications@github.com>", ME, "PR", "Hi", "g1@g")
    assert parse.parse(news, {ME})["is_bulk"] and parse.parse(bot, {ME})["is_bulk"]


def test_a_reply_from_you_settles_the_conversation():
    acc = account()
    ask = parse.parse(raw("Sarah <sarah@acme.com>", ME, "Q4", "Approve?", "q1@acme"), {ME})
    for key in sync._save_messages(acc, [ask]):
        sync.rebuild_thread(acc, key)
    t = get_db().execute("SELECT * FROM email_threads").fetchone()
    assert t["last_from_me"] == 0 and t["me_direct"] == 1 and t["counterpart_email"] == "sarah@acme.com"
    reply = parse.parse(raw(f"Luis <{ME}>", "sarah@acme.com", "Re: Q4", "Approved.", "q2@vora", refs="q1@acme"), {ME})
    reply["sent_at"] = "2026-09-26T10:00:00+00:00"
    for key in sync._save_messages(acc, [reply]):
        sync.rebuild_thread(acc, key)
    t = get_db().execute("SELECT * FROM email_threads").fetchone()
    assert t["last_from_me"] == 1 and t["status"] == "done"


def test_triage_uses_rules_first_then_the_ai(monkeypatch):
    acc = account()
    msgs = [parse.parse(raw("Sarah <sarah@acme.com>", ME, "Q4", "Please approve the budget by Tuesday.", "a1@x"), {ME}),
            parse.parse(raw("Tom <tom@x.com>", f"team@x.com, {ME}".replace(f", {ME}", ""), "FYI", "cc only", "c1@x",
                            extra=f"Cc: {ME}\r\n"), {ME}),
            parse.parse(raw("Deals <deals@shop.com>", ME, "Sale", "50% off", "s1@x",
                            extra="List-Unsubscribe: <mailto:u@shop.com>\r\n"), {ME})]
    for key in sync._save_messages(acc, msgs):
        sync.rebuild_thread(acc, key)
    sent = []

    def fake_complete(system, user, max_tokens, on_text=None, purpose=""):
        sent.append((user, purpose))
        return json.dumps([{"id": "acc:a1@x", "needs_reply": True, "reason": "Asks you to approve the budget",
                            "urgency": "high", "tasks": [{"direction": "mine", "owner": "Luis", "task": "Approve budget", "due": ""}]},
                           {"id": "acc:someone-else", "needs_reply": True}])
    monkeypatch.setattr(notes, "_complete", fake_complete)
    urgent = triage.run()
    assert len(sent) == 1 and sent[0][1] == "email"
    assert "Please approve the budget" in sent[0][0] and "cc only" not in sent[0][0] and "50% off" not in sent[0][0]
    assert [t["id"] for t in sync.waiting()] == ["acc:a1@x"]
    assert sync.waiting()[0]["tasks"][0]["task"] == "Approve budget"
    assert [u["id"] for u in urgent] == ["acc:a1@x"] and triage.run() == []  # notified once


def test_connecting_checks_the_login_and_keeps_the_password_in_the_keychain(monkeypatch, clean):
    logins = []
    monkeypatch.setattr(imap, "connect", lambda h, p, u, pw: logins.append((h, p, u, pw)) or NS(logout=lambda: None))
    r = client.post("/api/email/accounts", json={"provider": "gmail", "address": ME, "password": "abcd efgh ijkl mnop"})
    assert r.status_code == 200
    assert logins == [("imap.gmail.com", 993, ME, "abcdefghijklmnop")]  # Google shows app passwords with spaces
    assert clean == {f"email_password:{r.json()['id']}": "abcdefghijklmnop"}
    assert "password" not in json.dumps(client.get("/api/email/accounts").json())


def test_bad_login_is_explained_and_nothing_is_saved(monkeypatch):
    def refuse(*a):
        raise imap.imaplib.IMAP4.error("AUTHENTICATIONFAILED")
    monkeypatch.setattr(imap, "connect", refuse)
    r = client.post("/api/email/accounts", json={"provider": "gmail", "address": ME, "password": "wrongpass"})
    assert r.status_code == 400 and "app password" in r.json()["detail"]
    assert client.get("/api/email/accounts").json() == {"accounts": []}


def test_email_is_a_pro_feature():
    set_setting("license_status", {"valid": False})
    assert client.get("/api/email/waiting").status_code == 402
    r = client.post("/api/email/accounts", json={"provider": "gmail", "address": ME, "password": "abcdefgh"})
    assert r.status_code == 402 and r.json()["detail"]["feature"] == "email"


class FakeImap:
    """Answers like imaplib does against Gmail: LIST, SELECT, UID SEARCH, UID FETCH."""
    def __init__(self):
        self.untagged_responses = {}
        self.readonly = []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']

    def select(self, name, readonly=False):
        self.readonly.append(readonly)
        self.untagged_responses = {"UIDVALIDITY": [b"7"]}
        return "OK", [b"2"]

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            return "OK", [b"41 42"]
        head = b"From: Sarah <sarah@acme.com>\r\nTo: luis@vora.co\r\nSubject: Hi\r\nMessage-ID: <m@x>\r\n\r\n"
        return "OK", [(b"1 (UID 41 BODY[HEADER] {90}", head), (b" BODY[TEXT]<0> {5}", b"Hello"), b" X-GM-THRID 1777)",
                      (b"2 (X-GM-THRID 1888 UID 42 BODY[HEADER] {90}", head), (b" BODY[TEXT]<0> {3}", b"Yo!"), b")"]


def test_imap_fetch_reads_messages_threads_and_cursors_read_only():
    conn, state = FakeImap(), {}
    got = imap.fetch_new(conn, state, gmail=True)
    assert [(kind, thread) for kind, _, thread in got] == [("inbox", "1777"), ("inbox", "1888"), ("sent", "1777"), ("sent", "1888")]
    assert got[0][1].endswith(b"Hello") and parse.parse(got[0][1], {ME}, got[0][2])["thread_key"] == "1777"
    assert state == {"inbox": {"validity": "7", "last_uid": 42}, "sent": {"validity": "7", "last_uid": 42}}
    assert conn.readonly == [True, True]  # never changes anything on the server
