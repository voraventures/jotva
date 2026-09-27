"""Speaker setup and a distinct metadata-only capability for the native host."""
import hmac
import secrets
import time
import json
import threading
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from ..services import speaker_models, speakers
from ..db import get_db, get_setting
from ..config import is_safe_managed_path, write_secure_text
from ..services.speaker_capture import capture

router = APIRouter(prefix="/api/speakers", tags=["speakers"])
BRIDGE_TOKEN = secrets.token_urlsafe(32)
_retry_lock = threading.Lock()


def bridge_auth(request: Request, x_speaker_bridge: str = Header(default="")):
    if request.headers.get("origin") or not hmac.compare_digest(x_speaker_bridge, BRIDGE_TOKEN):
        raise HTTPException(401, "Unauthorized")


bridge_router = APIRouter(prefix="/speaker-bridge", dependencies=[Depends(bridge_auth)])


class Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["meet", "zoom"]
    target: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    url: str | None = Field(default=None, max_length=512)


class Participant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")


class Activity(Offer):
    connection: Literal['connected', 'unavailable', 'disconnected'] = 'connected'
    session: str = Field(min_length=20, max_length=100)
    observed_at: float = Field(allow_inf_nan=False)
    participants: list[Participant] = Field(max_length=20)


@router.get("/status")
def status():
    return {"models": speaker_models.status(), "platforms_qualified": False, "activity": capture.connection_status()}


@router.post("/models/install")
def install():
    speaker_models.install()
    return speaker_models.status()


@router.post("/models/cancel")
def cancel():
    speaker_models.cancel()
    return {"ok": True}


@router.post("/{meeting_id}/retry")
def retry(meeting_id: str):
    # Only recover this release's failed analysis; never rewrite legacy meetings.
    if not _retry_lock.acquire(blocking=False):
        raise HTTPException(409, "Speaker analysis already running")
    try:
        db = get_db()
        row = db.execute("SELECT t.*,m.audio_path,m.transcript_path,m.status FROM transcripts t JOIN meetings m ON m.id=t.meeting_id WHERE t.meeting_id=?", (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Transcript not found")
        analysis = json.loads(row["speaker_analysis"] or "{}")
        if row['status'] not in ('ready', 'error') or analysis.get('status') not in ('failed', 'models_missing') or not analysis.get('version'):
            raise HTTPException(409, "Analysis is not recoverable")
        if not get_setting('speaker_identification', True) or not speaker_models.ready():
            raise HTTPException(409, "Set up speaker identification first")
        if not row['audio_path'] or not is_safe_managed_path(row['audio_path']) or not Path(row['audio_path']).is_file():
            raise HTTPException(409, "Recording audio unavailable")
        if not row['transcript_path'] or not is_safe_managed_path(row['transcript_path']):
            raise HTTPException(409, "Transcript file unavailable")
        result = speakers.analyze(meeting_id, row['audio_path'], {'text': row['text'], 'segments': json.loads(row['segments'] or '[]')})
        db.execute('BEGIN IMMEDIATE')
        try:
            if not db.execute('SELECT 1 FROM meetings WHERE id=?', (meeting_id,)).fetchone():
                raise HTTPException(404, 'Meeting deleted')
            write_secure_text(row['transcript_path'], result['text'])
            db.execute('UPDATE transcripts SET text=?,segments=?,speaker_analysis=? WHERE meeting_id=?', (result['text'], json.dumps(result['segments']), json.dumps(result['speaker_analysis']), meeting_id))
            db.commit()
        except Exception:
            db.rollback()
            raise
        return result['speaker_analysis']
    finally:
        _retry_lock.release()


@bridge_router.get("/state")
def state():
    return {"active": capture.available(), "now": time.time()}


@bridge_router.post("/offer")
def offer(body: Offer):
    return capture.offer(body.source, body.target, body.url)


@bridge_router.post("/activity")
def activity(body: Activity):
    return {"accepted": capture.ingest(body.session, body.source, body.target, body.observed_at,
                                       [p.model_dump() for p in body.participants], body.connection)}
