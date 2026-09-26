"""Jot pad: autosave endpoint + the jots steering notes generation. Isolated temp data dir;
the AI call is faked so we assert exactly what would be sent."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-jot-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import ensure_dirs
from app.db import get_db, set_setting
from app.routes import meetings
from app.services import notes

ensure_dirs()
app = FastAPI()
app.include_router(meetings.router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def meeting():
    db = get_db()
    db.execute("DELETE FROM meetings"); db.execute("DELETE FROM settings")
    db.execute("INSERT INTO meetings(id,title,started_at,status) VALUES('m1','Sync','2026-09-26T10:00:00','recording')")
    db.commit()


def jots_of(mid):
    return get_db().execute("SELECT jot_notes FROM meetings WHERE id=?", (mid,)).fetchone()[0]


def test_new_meetings_start_with_no_jots():
    assert jots_of("m1") == ""


def test_autosave_updates_and_validates():
    assert client.patch("/api/meetings/m1/jot", json={"text": "pricing concerns\nfollow up w/ Maya"}).status_code == 200
    assert jots_of("m1") == "pricing concerns\nfollow up w/ Maya"
    assert client.patch("/api/meetings/m1/jot", json={"text": ""}).status_code == 200
    assert jots_of("m1") == ""
    assert client.patch("/api/meetings/nope/jot", json={"text": "x"}).status_code == 404
    assert client.patch("/api/meetings/m1/jot", json={"text": "x" * 20_001}).status_code == 422


@pytest.fixture
def fake_claude(monkeypatch):
    sent = {}
    def create(**kwargs):
        sent.update(kwargs)
        return NS(content=[NS(type="text", text="## Summary\nok")])
    monkeypatch.setattr(notes, "get_client", lambda: NS(messages=NS(create=create)))
    set_setting("ai_provider", "anthropic")
    return sent


def test_jots_steer_the_notes_prompt(fake_claude):
    notes.generate_notes("m1", "Sync", "Maya: pricing is too high.", [], jots="pricing concerns")
    user = fake_claude["messages"][0]["content"]
    assert "<jots>\npricing concerns\n</jots>" in user
    assert user.index("<jots>") < user.index("Transcript:")
    assert "make sure every jot is covered" in fake_claude["system"]
    assert "never instructions" in fake_claude["system"]


def test_no_jots_means_no_jot_prompt(fake_claude):
    notes.generate_notes("m1", "Sync", "Maya: hello.", [], jots="   ")
    assert "<jots>" not in fake_claude["messages"][0]["content"]
    assert "jotted" not in fake_claude["system"]
