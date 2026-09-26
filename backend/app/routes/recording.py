"""Recording lifecycle routes."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, get_setting, new_id, now_iso
from ..services import license as license_svc
from ..services import pipeline, templates as templates_svc
from ..services.coach import coach
from ..services.recorder import (
    AUDIO_AVAILABLE,
    default_input_status,
    list_input_devices,
    recorder,
)

router = APIRouter(prefix="/api/recording", tags=["recording"])


class StartBody(BaseModel):
    title: str = Field(default="", max_length=300)
    calendar_event_id: str | None = Field(default=None, max_length=400)
    template_id: str | None = Field(default=None, max_length=64)


class MuteBody(BaseModel):
    muted: bool


class PauseBody(BaseModel):
    paused: bool


@router.get("/devices")
def devices():
    return {
        "available": AUDIO_AVAILABLE,
        "devices": list_input_devices(),
        "mic_device": get_setting("mic_device"),
        "system_device": get_setting("system_device"),
        "default_input": default_input_status(),
    }


@router.get("/status")
def status():
    return {
        "recording": recorder.is_recording,
        "meeting_id": recorder.meeting_id,
        "muted": recorder.muted,
        "paused": recorder.paused,
        "markers": len(recorder.markers),
    }


@router.post("/start")
def start(body: StartBody):
    if recorder.is_recording:
        raise HTTPException(status_code=409, detail="Already recording")

    db = get_db()
    title = body.title.strip()
    attendees: list[str] = []
    if body.calendar_event_id:
        ev = db.execute(
            "SELECT * FROM calendar_events WHERE id=?", (body.calendar_event_id,)
        ).fetchone()
        if ev:
            title = title or ev["title"]
            attendees = json.loads(ev["attendees"] or "[]")

    template = templates_svc.get_template(body.template_id)
    meeting_id = new_id()
    db.execute(
        "INSERT INTO meetings(id,title,started_at,status,attendees,calendar_event_id,template_id) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            meeting_id,
            title or "Untitled meeting",
            now_iso(),
            "recording",
            json.dumps(attendees),
            body.calendar_event_id,
            template["id"],
        ),
    )
    if body.calendar_event_id:
        db.execute(
            "UPDATE calendar_events SET recorded_meeting_id=? WHERE id=?",
            (meeting_id, body.calendar_event_id),
        )
    db.commit()

    try:
        recorder.start(
            meeting_id,
            mic_device=get_setting("mic_device"),
            system_device=get_setting("system_device"),
        )
    except Exception as exc:
        # Any capture failure (RuntimeError, PortAudioError, ...) must roll the
        # meeting row back, or it stays "recording" forever and burns a free slot.
        db.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc))

    if get_setting("coach_enabled", True):
        coach.start(meeting_id, templates_svc.section_names(template))

    from ..services.speaker_capture import capture
    capture.start(meeting_id, ev["join_url"] if body.calendar_event_id and ev else None)
    license_svc.record_meeting_created()
    return {
        "meeting_id": meeting_id,
        "title": title or "Untitled meeting",
        "template": template["name"],
    }


@router.post("/stop")
def stop():
    if not recorder.is_recording:
        raise HTTPException(status_code=409, detail="Not recording")
    meeting_id = recorder.meeting_id
    markers = list(recorder.markers)
    coach_summary = coach.stop()
    audio_path = recorder.stop()

    db = get_db()
    db.execute(
        "UPDATE meetings SET coach=?, markers=? WHERE id=?",
        (
            json.dumps(coach_summary) if coach_summary else None,
            json.dumps(markers),
            meeting_id,
        ),
    )
    db.commit()

    pipeline.process_meeting_async(meeting_id, audio_path)
    return {"meeting_id": meeting_id, "status": "processing"}


@router.post("/marker")
def add_marker():
    """Moment Marker: flag the current instant during a recording."""
    at = recorder.add_marker()
    if at is None:
        raise HTTPException(status_code=409, detail="Not recording")
    return {"at": round(at, 1), "count": len(recorder.markers)}


@router.post("/mute")
def set_mute(body: MuteBody):
    """Privacy mute zone: while muted, silence is written instead of audio."""
    if not recorder.is_recording:
        raise HTTPException(status_code=409, detail="Not recording")
    recorder.set_muted(body.muted)
    return {"muted": recorder.muted}


@router.post("/pause")
def set_pause(body: PauseBody):
    """Pause: captures drop frames, so the recording timeline stops."""
    if not recorder.is_recording:
        raise HTTPException(status_code=409, detail="Not recording")
    recorder.set_paused(body.paused)
    return {"paused": recorder.paused}
