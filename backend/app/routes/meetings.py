"""Meeting CRUD, notes retrieval, search."""
import json
import secrets as _secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_db, new_id, now_iso, row_to_dict
from ..services import intelligence, license as license_svc, notes as notes_svc, pipeline

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class RenameBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    starred: bool | None = None


class MeetingAskBody(BaseModel):
    query: str = Field(min_length=3, max_length=300)


class CreateMeetingBody(BaseModel):
    """Create a fully-formed meeting from supplied notes (used by the onboarding
    demo). Action items / decisions / topics are derived from notes_markdown the
    same way the recording pipeline does, so the meeting behaves like a real one."""
    title: str = Field(min_length=1, max_length=300)
    date: str | None = Field(default=None, max_length=64)
    attendees: list[str] = Field(default_factory=list)
    notes_markdown: str = Field(min_length=1, max_length=200000)
    # Accepted for API compatibility; content is derived from notes_markdown.
    source: str | None = None
    duration_seconds: int | None = None
    context: str | None = None
    key_discussions: str | None = None
    decisions: list | None = None
    action_items: list | None = None


class JotBody(BaseModel):
    text: str = Field(max_length=20_000)


class RegenerateBody(BaseModel):
    template_id: str | None = Field(default=None, max_length=64)


class FollowupBody(BaseModel):
    tone: str = Field(default="professional", pattern="^(professional|friendly|concise)$")


@router.get("")
def list_meetings():
    db = get_db()
    rows = db.execute(
        """SELECT m.*,
             (SELECT COUNT(*) FROM action_items a WHERE a.meeting_id=m.id AND a.status='open') AS open_actions
           FROM meetings m ORDER BY m.started_at DESC"""
    ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.post("")
def create_meeting(body: CreateMeetingBody):
    """Insert a ready-to-view meeting plus its notes, then index actions/
    decisions/topics from the markdown (mirrors pipeline._generate_and_index).
    The only caller is the onboarding demo loader, so every meeting created
    here is flagged is_demo so it can never be mistaken for real AI output."""
    db = get_db()
    meeting_id = new_id()
    started = (body.date or now_iso()).strip() or now_iso()
    try:
        datetime.fromisoformat(started)
    except ValueError:
        # A non-ISO date stored here would 500 every later fromisoformat over
        # the meetings table (e.g. the series view) until the row is fixed.
        raise HTTPException(status_code=422, detail="date must be an ISO-8601 datetime")
    db.execute(
        "INSERT INTO meetings(id,title,started_at,ended_at,status,attendees,is_demo) "
        "VALUES(?,?,?,?,?,?,1)",
        (meeting_id, body.title.strip(), started, now_iso(), "ready",
         json.dumps([a for a in body.attendees if isinstance(a, str)])),
    )
    sections = notes_svc.split_sections(body.notes_markdown)
    db.execute(
        "INSERT OR REPLACE INTO notes(meeting_id,content,sections,generated_at) "
        "VALUES(?,?,?,?)",
        (meeting_id, body.notes_markdown, json.dumps(sections), now_iso()),
    )
    db.commit()
    intelligence.index_notes(meeting_id, body.notes_markdown)
    return {"id": meeting_id, "meeting_id": meeting_id}


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=200)):
    """Full-text search across titles, notes, transcripts, and action items."""
    # Escape LIKE wildcards so a literal % or _ in the query matches itself.
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{escaped}%"
    db = get_db()
    rows = db.execute(
        """SELECT DISTINCT m.* FROM meetings m
           LEFT JOIN notes n ON n.meeting_id = m.id
           LEFT JOIN transcripts t ON t.meeting_id = m.id
           LEFT JOIN action_items a ON a.meeting_id = m.id
           WHERE m.title LIKE ? ESCAPE '\\' OR n.content LIKE ? ESCAPE '\\'
              OR t.text LIKE ? ESCAPE '\\' OR a.action LIKE ? ESCAPE '\\'
              OR a.owner LIKE ? ESCAPE '\\'
           ORDER BY m.started_at DESC LIMIT 50""",
        (like, like, like, like, like),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


@router.get("/{meeting_id}")
def get_meeting(meeting_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Meeting not found")
    meeting = row_to_dict(row)

    note = db.execute(
        "SELECT content, sections, generated_at FROM notes WHERE meeting_id=?",
        (meeting_id,),
    ).fetchone()
    meeting["notes"] = (
        {
            "content": note["content"],
            "sections": json.loads(note["sections"] or "{}"),
            "generated_at": note["generated_at"],
        }
        if note
        else None
    )
    transcript = db.execute(
        "SELECT text, language, duration_sec, segments, speaker_analysis FROM transcripts WHERE meeting_id=?",
        (meeting_id,),
    ).fetchone()
    meeting["transcript"] = dict(transcript) if transcript else None
    if meeting["transcript"]:
        try:
            meeting["transcript"]["speaker_analysis"] = json.loads(meeting["transcript"].get("speaker_analysis") or "{}")
        except (TypeError, ValueError):
            meeting["transcript"]["speaker_analysis"] = {}
        # Parse segments JSON for the diarized transcript view in the UI
        raw_segs = meeting["transcript"].pop("segments", None)
        if raw_segs:
            try:
                meeting["transcript"]["_segments"] = json.loads(raw_segs)
            except (json.JSONDecodeError, TypeError):
                meeting["transcript"]["_segments"] = []
        else:
            meeting["transcript"]["_segments"] = []
    meeting["intelligence"] = intelligence.meeting_intelligence(meeting_id)
    meeting["coach"] = json.loads(meeting["coach"]) if meeting.get("coach") else None
    try:
        meeting["markers"] = json.loads(meeting.get("markers") or "[]")
    except (json.JSONDecodeError, TypeError):
        meeting["markers"] = []
    from ..services.conflicts import conflicts_for_meeting

    meeting["conflicts"] = conflicts_for_meeting(meeting_id)
    return meeting


@router.patch("/{meeting_id}/jot")
def save_jot(meeting_id: str, body: JotBody):
    """Autosaved jot pad: the user's own notes, used to steer the AI notes."""
    db = get_db()
    updated = db.execute("UPDATE meetings SET jot_notes=? WHERE id=?", (body.text, meeting_id)).rowcount
    db.commit()  # always end the write transaction, or this thread's connection keeps the DB locked
    if not updated:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"ok": True}


@router.patch("/{meeting_id}")
def rename_meeting(meeting_id: str, body: RenameBody):
    db = get_db()
    sets, params = [], []
    if body.title is not None:
        sets.append("title=?")
        params.append(body.title.strip())
    if body.starred is not None:
        sets.append("starred=?")
        params.append(1 if body.starred else 0)
    if not sets:
        raise HTTPException(status_code=422, detail="Nothing to update")
    cur = db.execute(
        f"UPDATE meetings SET {', '.join(sets)} WHERE id=?", (*params, meeting_id)
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"ok": True}


@router.get("/{meeting_id}/audio")
def meeting_audio(meeting_id: str):
    """Stream the recording so the transcript playback bar can seek it."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from ..config import RECORDINGS_DIR

    db = get_db()
    row = db.execute(
        "SELECT audio_path FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()
    if not row or not row["audio_path"]:
        raise HTTPException(status_code=404, detail="No recording for this meeting")
    path = Path(row["audio_path"])
    # only serve files that actually live in the recordings dir
    if not path.is_file() or RECORDINGS_DIR.resolve() not in path.resolve().parents:
        raise HTTPException(status_code=404, detail="Recording file not found")
    return FileResponse(path, media_type="audio/wav")


@router.post("/{meeting_id}/ask")
def ask_meeting_route(meeting_id: str, body: MeetingAskBody):
    """Answer a question about this meeting from its notes and transcript."""
    from ..services.ai import ask_meeting

    try:
        return ask_meeting(meeting_id, body.query.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: str):
    db = get_db()
    row = db.execute("SELECT audio_path, transcript_path, notes_path FROM meetings WHERE id=?",
                     (meeting_id,)).fetchone()
    cur = db.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _delete_meeting_files(meeting_id, row)
    return {"ok": True}


def _delete_meeting_files(meeting_id: str, row) -> None:
    """The delete dialog promises the recording, transcript and notes are removed:
    remove the files too, not just the database row. Only paths inside Jotva's
    own folders are touched."""
    from pathlib import Path

    from ..config import DATA_DIR, NOTES_DIR, RECORDINGS_DIR, TRANSCRIPTS_DIR

    candidates = [RECORDINGS_DIR / f"{meeting_id}{suffix}" for suffix in (".wav", ".loudness.json", ".transcript_partial.json")]
    candidates += [TRANSCRIPTS_DIR / f"{meeting_id}.txt", NOTES_DIR / f"{meeting_id}.md"]
    if row:
        candidates += [Path(p) for p in (row["audio_path"], row["transcript_path"], row["notes_path"]) if p]
    root = DATA_DIR.resolve()
    for path in candidates:
        try:
            resolved = path.resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                resolved.unlink()
        except OSError:
            pass


class SpeakerNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.post("/{meeting_id}/speakers/{speaker_id}")
def name_speaker(meeting_id: str, speaker_id: str, body: SpeakerNameBody):
    """Click-to-correct: give one of the meeting's voices a name. Every line of
    that voice is relabeled, and the notes' generic "Speaker N" mentions and
    action-item owners follow."""
    name = body.name.strip()
    db = get_db()
    row = db.execute("SELECT segments FROM transcripts WHERE meeting_id=?", (meeting_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Meeting not found")
    segments = json.loads(row["segments"] or "[]")
    old_labels = {s.get("speaker") for s in segments if s.get("speaker_id") == speaker_id}
    if not old_labels:
        raise HTTPException(status_code=404, detail="Speaker not found")
    for seg in segments:
        if seg.get("speaker_id") == speaker_id:
            seg.update(speaker=name, speaker_name=name, speaker_source="user")
    text = "\n".join(f"{s['speaker']}: {s['text']}" for s in segments if s.get("speaker"))
    db.execute("UPDATE transcripts SET segments=?, text=? WHERE meeting_id=?", (json.dumps(segments), text, meeting_id))
    generic = f"Speaker {speaker_id.rsplit('_', 1)[-1]}"
    note = db.execute("SELECT content FROM notes WHERE meeting_id=?", (meeting_id,)).fetchone()
    if note and generic in note["content"]:
        import re as _re

        content = _re.sub(rf"\b{_re.escape(generic)}\b", name, note["content"])
        db.execute("UPDATE notes SET content=? WHERE meeting_id=?", (content, meeting_id))
    db.execute("UPDATE action_items SET owner=? WHERE meeting_id=? AND owner IN (%s)" % ",".join("?" * len(old_labels | {generic})),
               (name, meeting_id, *(old_labels | {generic})))
    db.commit()
    return {"ok": True}


@router.post("/{meeting_id}/share")
def create_share(meeting_id: str):
    """Mint a read-only share token (30-day expiry) for this meeting."""
    db = get_db()
    if not db.execute("SELECT 1 FROM meetings WHERE id=?", (meeting_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Meeting not found")
    token = _secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    db.execute(
        "INSERT INTO shares(id,meeting_id,token,created_at,expires_at) VALUES(?,?,?,?,?)",
        (new_id(), meeting_id, token, now.isoformat(), expires.isoformat()),
    )
    db.commit()
    return {
        "share_url": f"jotva://share/{token}",
        "token": token,
        "expires_at": expires.isoformat(),
    }


@router.post("/{meeting_id}/regenerate")
def regenerate(meeting_id: str, body: RegenerateBody | None = None):
    db = get_db()
    if not db.execute("SELECT 1 FROM meetings WHERE id=?", (meeting_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not license_svc.can_write_ai_notes(meeting_id):
        raise HTTPException(status_code=402, detail={
            "code": "ai_limit", "feature": "unlimited_notes",
            "message": "You've used this month's free AI notes. Upgrade to Pro for unlimited notes."})
    pipeline.regenerate_notes_async(
        meeting_id, template_id=body.template_id if body else None
    )
    return {"ok": True}


@router.post("/{meeting_id}/followup")
def compose_followup(meeting_id: str, body: FollowupBody):
    """Smart Follow-up Composer: Claude drafts the email from the notes."""
    from ..services.ai import compose_followup as compose

    license_svc.require_pro("followup")

    try:
        draft = compose(meeting_id, body.tone)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db = get_db()
    row = db.execute(
        "SELECT attendees FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()
    attendees = json.loads(row["attendees"]) if row else []
    return {**draft, "attendees": attendees}


@router.post("/{meeting_id}/share-to-workspace")
def share_to_workspace(meeting_id: str):
    """Share a meeting to the team workspace."""
    from .workspace import share_meeting_to_workspace

    license_svc.require_pro("integrations")

    try:
        return share_meeting_to_workspace(meeting_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{meeting_id}/followup/sent")
def mark_followup_sent(meeting_id: str):
    db = get_db()
    cur = db.execute(
        "UPDATE meetings SET followup_sent=1 WHERE id=?", (meeting_id,)
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"ok": True}
