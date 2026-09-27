"""Naming voices from the calendar invite without voiceprints: the note-taker from
mic-vs-call loudness, others only from clear conversational clues, checked
against the attendee list. The AI is faked; no audio models are used."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-speaker-name-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.config import ensure_dirs
from app.services import notes, speakers
from app.services.recorder import track_loudness_path

ensure_dirs()


def test_email_attendees_become_readable_names():
    assert speakers.display_name("sarah.lee@acme.com") == "Sarah Lee"
    assert speakers.display_name("Marcus Diaz") == "Marcus Diaz"


def test_note_taker_is_the_voice_on_this_macs_mic():
    # 0-10 s: loud on the mic (the user); 10-20 s: loud on the call audio (remote)
    track_loudness_path("m1").write_text(json.dumps(
        {"step": 0.25, "mic": [0.2] * 40 + [0.01] * 40, "system": [0.01] * 40 + [0.3] * 40}))
    turns = [{"start": 0, "end": 10, "speaker_id": "speaker_1"}, {"start": 10, "end": 20, "speaker_id": "speaker_2"}]
    assert speakers.note_taker_speaker("m1", turns) == "speaker_1"


def test_no_note_taker_without_both_tracks():
    turns = [{"start": 0, "end": 10, "speaker_id": "speaker_1"}]
    assert speakers.note_taker_speaker("no-such-meeting", turns) is None


def test_context_names_only_accepts_invited_people(monkeypatch):
    monkeypatch.setattr(notes, "identify_speakers", lambda transcript, attendees: {
        "Speaker 2": "Sarah Lee",        # invited: accepted
        "Speaker 3": "Somebody Else",    # not on the invite: dropped
        "Speaker 1": "Marcus Diaz",      # already named from the mic: ignored
    })
    segments = [{"speaker_id": f"speaker_{i}", "speaker": f"Speaker {i}", "text": "hi"} for i in (1, 2, 3)]
    names = {"speaker_1": {"name": "Luis Coomer", "source": "mic"}}
    found = speakers.context_names(segments, ["Sarah Lee", "Marcus Diaz", "Luis Coomer"], names)
    assert found == {"speaker_2": {"name": "Sarah Lee", "source": "context"}}


def test_ai_failure_leaves_speakers_unnamed(monkeypatch):
    def boom(*a):
        raise RuntimeError("offline")
    monkeypatch.setattr(notes, "identify_speakers", boom)
    segments = [{"speaker_id": "speaker_2", "speaker": "Speaker 2", "text": "hi"}]
    assert speakers.context_names(segments, ["Sarah Lee"], {}) == {}


def test_renaming_a_speaker_relabels_transcript_notes_and_owners():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.db import get_db
    from app.routes import meetings

    app = FastAPI(); app.include_router(meetings.router); client = TestClient(app)
    db = get_db()
    db.execute("INSERT INTO meetings(id,title,started_at,status) VALUES('r1','Sync','2026-09-26T10:00:00','ready')")
    segs = [{"start": 0, "end": 2, "text": "I'll send it.", "speaker_id": "speaker_2", "speaker": "Speaker 2"},
            {"start": 2, "end": 3, "text": "Thanks.", "speaker_id": "speaker_1", "speaker": "Luis Coomer"}]
    db.execute("INSERT INTO transcripts(meeting_id,text,segments) VALUES('r1','',?)", (json.dumps(segs),))
    db.execute("INSERT INTO notes VALUES('r1','Speaker 2 will send the deck. Speaker 20 is someone else.','{}','x')")
    db.execute("INSERT INTO action_items(id,meeting_id,owner,action,due) VALUES('rename-a1','r1','Speaker 2','Send deck','')")
    db.commit()
    assert client.post("/api/meetings/r1/speakers/speaker_2", json={"name": "Sarah Lee"}).status_code == 200
    saved = json.loads(db.execute("SELECT segments FROM transcripts WHERE meeting_id='r1'").fetchone()[0])
    assert saved[0]["speaker"] == "Sarah Lee" and saved[1]["speaker"] == "Luis Coomer"
    assert db.execute("SELECT content FROM notes WHERE meeting_id='r1'").fetchone()[0] == \
        "Sarah Lee will send the deck. Speaker 20 is someone else."
    assert db.execute("SELECT owner FROM action_items WHERE id='rename-a1'").fetchone()[0] == "Sarah Lee"
    assert client.post("/api/meetings/r1/speakers/speaker_9", json={"name": "X"}).status_code == 404
