"""Freemium plan: free = unlimited recording + FREE_AI_NOTES_PER_MONTH bundled-AI notes
a month; Pro unlocks unlimited notes and the power features. Isolated temp data dir;
keychain and AI are faked so nothing touches the real Mac or the network."""
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-freemium-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import ensure_dirs
from app.db import get_db, get_setting, set_setting
from app.routes import calendar, meetings, misc
from app.services import conflicts, license, notes, pipeline, telemetry

ensure_dirs()
app = FastAPI()
app.include_router(meetings.router)
app.include_router(calendar.router)
app.include_router(misc.router)
client = TestClient(app)
LIMIT = license.FREE_AI_NOTES_PER_MONTH


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    secrets = {}
    monkeypatch.setattr(license, "_keyring", None)  # never touch the real keychain
    monkeypatch.setattr(license, "get_secret", lambda name: secrets.get(name))
    monkeypatch.setattr(license, "_sync_install_id_key", lambda: None)
    monkeypatch.setattr(notes, "generate_notes",
                        lambda *a, **k: {"content": "## Summary\nok", "path": ""})
    monkeypatch.setattr(pipeline.intelligence, "index_notes", lambda *a, **k: None)
    monkeypatch.setattr(conflicts, "detect_conflicts", lambda *a, **k: None)
    monkeypatch.setattr(telemetry, "emit", lambda *a, **k: None)
    db = get_db()
    for table in ("ai_note_usage", "notes", "meetings", "settings"):
        db.execute(f"DELETE FROM {table}")
    db.commit()
    set_setting("ai_provider", "anthropic")
    set_setting("license_status", {"valid": False})
    return secrets


def add_meeting(mid):
    db = get_db()
    db.execute("INSERT INTO meetings(id,title,started_at,status) VALUES(?,?,?,?)",
               (mid, "Sync", "2026-09-26T10:00:00", "generating"))
    db.commit()


def write_notes(mid):
    add_meeting(mid)
    pipeline._generate_and_index(mid, "Maya: hello.", [])
    return get_db().execute("SELECT ai_paused FROM meetings WHERE id=?", (mid,)).fetchone()[0]


def has_notes(mid):
    return get_db().execute("SELECT 1 FROM notes WHERE meeting_id=?", (mid,)).fetchone() is not None


def test_free_plan_records_forever_and_reports_its_allowance():
    s = license.status()
    assert s["tier"] == "free" and s["can_record"] is True
    assert s["ai_notes_limit"] == LIMIT and s["ai_notes_remaining"] == LIMIT
    assert s["features"]["ask_all"] is False and s["features"]["mcp"] is False


def test_free_notes_pause_after_the_monthly_allowance():
    for i in range(LIMIT):
        assert write_notes(f"m{i}") == 0 and has_notes(f"m{i}")
    assert license.status()["ai_notes_remaining"] == 0
    assert write_notes("over") == 1 and not has_notes("over")  # transcript kept, notes paused


def test_regenerating_a_counted_meeting_is_free():
    for i in range(LIMIT):
        write_notes(f"m{i}")
    pipeline._generate_and_index("m0", "Maya: hello again.", [])
    assert license.ai_notes_used() == LIMIT


def test_regenerate_route_offers_upgrade_at_the_limit(monkeypatch):
    monkeypatch.setattr(pipeline, "regenerate_notes_async", lambda *a, **k: None)
    for i in range(LIMIT):
        write_notes(f"m{i}")
    add_meeting("over")
    r = client.post("/api/meetings/over/regenerate")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "ai_limit"
    assert client.post("/api/meetings/m0/regenerate").status_code == 200


def test_pro_is_unlimited_and_own_key_is_a_pro_feature(isolated):
    set_setting("license_status", {"valid": True, "dev": True})
    for i in range(LIMIT + 2):
        assert write_notes(f"p{i}") == 0
    assert license.status()["ai_notes_limit"] is None
    isolated["anthropic_api_key"] = "user-key"
    assert license.uses_bundled_ai() is False  # Pro + own key: the user's own account
    set_setting("license_status", {"valid": False})
    assert license.uses_bundled_ai() is True  # Free: an own key is ignored
    write_notes("byok")
    assert license.ai_notes_used() == 1  # so it counts against the free allowance


def test_pro_features_answer_402_on_free():
    add_meeting("m1")
    r = client.post("/api/meetings/m1/followup", json={"tone": "friendly"})
    assert r.status_code == 402 and r.json()["detail"]["feature"] == "followup"
    assert client.post("/api/meetings/m1/share-to-workspace").status_code == 402
    r = client.post("/api/calendar/mode", json={"mode": "all"})
    assert r.status_code == 402 and get_setting("recording_mode", None) is None
    assert client.post("/api/calendar/mode", json={"mode": "confirm_30s"}).status_code == 200


def test_pro_settings_and_routes_answer_402_on_free():
    for key, value, feature in (("mcp_enabled", True, "mcp"), ("recording_mode", "all", "auto_record"),
                                ("ai_quality", "pro", "higher_quality")):
        r = client.post("/api/settings", json={"key": key, "value": value})
        assert r.status_code == 402 and r.json()["detail"]["feature"] == feature
    assert client.post("/api/settings", json={"key": "mcp_enabled", "value": False}).status_code == 200
    assert client.post("/api/search/ask", json={"query": "pricing"}).status_code == 402
    r = client.post("/api/templates", json={"name": "Mine", "description": "", "body": "## Notes\n- summary"})
    assert r.status_code == 402 and r.json()["detail"]["feature"] == "templates"
    add_meeting("m1")
    assert client.post("/api/integrations/slack/send/m1").status_code == 402


def test_pro_can_turn_on_pro_settings():
    set_setting("license_status", {"valid": True, "dev": True})
    assert client.post("/api/settings", json={"key": "mcp_enabled", "value": True}).status_code == 200
    assert client.post("/api/settings", json={"key": "recording_mode", "value": "all"}).status_code == 200


def test_a_keychain_refusal_never_breaks_the_plan_status(monkeypatch):
    from app.routes import workspace

    def refuse(*a):
        raise RuntimeError("(-25244, 'Unknown Error')")
    monkeypatch.undo()  # use the real _sync_install_id_key
    monkeypatch.setattr(license, "_keyring", None)
    monkeypatch.setattr(license, "get_secret", lambda name: None)
    monkeypatch.setattr(license, "set_secret", refuse)
    monkeypatch.setattr(workspace, "_install_id", lambda: "a" * 32)
    assert license.status()["tier"] in ("free", "pro")
