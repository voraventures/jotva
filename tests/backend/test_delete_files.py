"""Deleting a meeting removes its files, as the delete dialog promises, and
never touches anything outside Jotva's own data folder."""
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-delete-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import NOTES_DIR, RECORDINGS_DIR, TRANSCRIPTS_DIR, ensure_dirs
from app.db import get_db
from app.routes import meetings

ensure_dirs()
app = FastAPI()
app.include_router(meetings.router)
client = TestClient(app)


def test_delete_removes_audio_transcript_notes_and_sidecars(tmp_path):
    outside = tmp_path / "keep.txt"
    outside.write_text("not jotva's")
    files = [RECORDINGS_DIR / "m1.wav", RECORDINGS_DIR / "m1.loudness.json",
             TRANSCRIPTS_DIR / "m1.txt", NOTES_DIR / "m1.md"]
    for f in files:
        f.write_text("x")
    db = get_db()
    db.execute("INSERT INTO meetings(id,title,started_at,status,audio_path,notes_path) VALUES(?,?,?,?,?,?)",
               ("m1", "Sync", "2026-09-26T10:00:00", "ready", str(files[0]), str(outside)))
    db.commit()
    assert client.delete("/api/meetings/m1").status_code == 200
    assert not any(f.exists() for f in files)
    assert outside.exists()  # a path outside Jotva's folder is never deleted
