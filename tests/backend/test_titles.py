"""Meeting names and notes quality: calendar and user-given names are kept, an
unnamed manual recording gets a suggested name, and the notes prompt carries the
meeting date and owner rules. The AI client is faked, so no network is used."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-title-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from app.config import ensure_dirs
from app.db import UNNAMED, get_db, set_setting
from app.services import conflicts, license, notes, pipeline, telemetry

ensure_dirs()


@pytest.fixture
def ai(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        text = "Weekly Priorities Planning" if kwargs["max_tokens"] <= 30 else "## Executive Summary\nPlanning."
        return NS(content=[NS(type="text", text=text)])

    monkeypatch.setattr(notes, "get_client", lambda: NS(messages=NS(create=create)))
    monkeypatch.setattr(pipeline.intelligence, "index_notes", lambda *a, **k: None)
    monkeypatch.setattr(conflicts, "detect_conflicts", lambda *a, **k: None)
    monkeypatch.setattr(telemetry, "emit", lambda *a, **k: None)
    monkeypatch.setattr(license, "can_write_ai_notes", lambda *a: True)
    monkeypatch.setattr(license, "record_ai_notes", lambda *a: None)
    db = get_db()
    for table in ("notes", "meetings", "settings"):
        db.execute(f"DELETE FROM {table}")
    db.commit()
    set_setting("ai_provider", "anthropic")
    set_setting("user_name", "Luis Coomer")
    return calls


def run(mid, title):
    db = get_db()
    db.execute("INSERT INTO meetings(id,title,started_at,status) VALUES(?,?,?,?)",
               (mid, title, "2026-09-26T19:31:17+00:00", "generating"))
    db.commit()
    pipeline._generate_and_index(mid, "I need to call John before Tuesday at 2 p.m.", [])
    return db.execute("SELECT title FROM meetings WHERE id=?", (mid,)).fetchone()[0]


def test_unnamed_manual_recording_gets_a_suggested_name(ai):
    assert run("m1", UNNAMED) == "Weekly Priorities Planning"
    assert len(ai) == 2 and ai[1]["max_tokens"] == 30


def test_given_names_are_never_replaced(ai):
    assert run("m2", "Board prep with Maya") == "Board prep with Maya"  # user- or calendar-named
    assert len(ai) == 1


def test_prompt_has_meeting_date_owner_and_due_rules(ai):
    run("m3", "Planning")
    call = ai[0]
    user = call["messages"][0]["content"]
    assert "Meeting date: " in user and "2026-09-2" in user
    assert "owned by Luis Coomer" in call["system"]
    assert "YYYY-MM-DD" in call["system"]
    assert "Do not restate action items" in call["system"]
