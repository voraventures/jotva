"""Live notes during recording (Pro): only Pro starts them, updates carry the
current notes plus only the new transcript, and small additions are skipped.
Recorder, AI and events are faked; nothing records or calls out."""
import os
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace as NS

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-live-pro-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from app.config import ensure_dirs
from app.db import set_setting
from app.services import license, live_notes as ln, notes

ensure_dirs()


@pytest.fixture
def setup(monkeypatch):
    calls, emitted = [], []

    def create(**kw):
        calls.append(kw)
        return NS(content=[NS(type="text", text=f"## Key points\n- update {len(calls)}")])

    monkeypatch.setattr(notes, "get_client", lambda: NS(messages=NS(create=create)))
    monkeypatch.setattr(ln.hub, "emit", lambda name, data: emitted.append((name, data)))
    monkeypatch.setattr(ln, "POLL", 0.01)
    monkeypatch.setattr(ln, "MIN_GAP", 0.0)
    fake = NS(_live_lock=threading.Lock(), _live_segments=[])
    monkeypatch.setattr(ln, "recorder", fake)
    set_setting("ai_provider", "anthropic")
    return calls, emitted, fake


def test_only_pro_gets_live_notes(monkeypatch, setup):
    monkeypatch.setattr(license, "is_pro", lambda: False)
    assert ln.LiveNotes().start("m1") is False


def test_updates_fold_new_transcript_into_current_notes(monkeypatch, setup):
    calls, emitted, rec = setup
    monkeypatch.setattr(license, "is_pro", lambda: True)
    live = ln.LiveNotes()
    rec._live_segments.append({"text": "Sarah will send the deck by Wednesday. " * 10})
    assert live.start("m1")
    for _ in range(200):
        if calls:
            break
        threading.Event().wait(0.01)
    rec._live_segments.append({"text": "ok"})  # too little new speech: no second call
    threading.Event().wait(0.1)
    live.stop()
    assert len(calls) == 1
    user = calls[0]["messages"][0]["content"]
    assert "(none yet)" in user and "Sarah will send the deck" in user
    assert calls[0]["extra_headers"] == {"x-jotva-purpose": "live"}
    assert emitted[0][0] == "live_notes" and emitted[0][1]["text"] == "## Key points\n- update 1"
