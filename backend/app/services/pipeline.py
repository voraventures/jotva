"""Recording → transcription → notes → intelligence pipeline (background thread)."""
import json
import logging
import threading
import wave
from pathlib import Path

import numpy as np

from ..config import RECORDINGS_DIR, write_secure_text
from ..db import close_db, get_db, now_iso
from ..events import hub
from . import intelligence, license, notes, transcriber, speakers

log = logging.getLogger("jotva.pipeline")

# Real speech peaks well above this even at low mic gain; digital silence
# (dead input device, e.g. a virtual/loopback device with nothing routed
# into it) reads as exactly 0.0. Catches that case before wasting a
# transcription pass and a paid notes-generation call on empty audio.
SILENCE_PEAK_THRESHOLD = 0.01


def _is_silent(audio_path: Path) -> bool:
    try:
        with wave.open(str(audio_path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        if not raw:
            return True
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
        return float(np.abs(data).max()) < SILENCE_PEAK_THRESHOLD
    except Exception:
        return False  # unreadable file — let transcription surface the real error


def _safe_error(exc: Exception) -> str:
    """Only our own RuntimeError messages reach the renderer; third-party
    exception text stays in server-side logs (C8)."""
    if isinstance(exc, RuntimeError):
        return str(exc)[:300]
    return "Processing failed — check the app logs for details."


def _set_status(meeting_id: str, status: str, error: str | None = None) -> None:
    db = get_db()
    db.execute(
        "UPDATE meetings SET status=?, error=? WHERE id=?", (status, error, meeting_id)
    )
    db.commit()
    hub.emit("meeting_status", {"meeting_id": meeting_id, "status": status, "error": error})


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _flagged_moments_section(markers: list, segments: list[dict]) -> str | None:
    """Build a deterministic 'Flagged Moments' section: verbatim transcript
    context (±20s) around each moment the user marked during the meeting."""
    if not markers or not segments:
        return None
    lines = []
    for marker in markers:
        window = [
            s["text"]
            for s in segments
            if s["end"] >= marker - 20 and s["start"] <= marker + 20
        ]
        if window:
            quote = " ".join(window).strip()[:400]
            lines.append(f'- **[{_fmt_ts(marker)}]** "{quote}"')
    if not lines:
        return None
    return "## Flagged Moments\n" + "\n".join(lines)


def _generate_and_index(meeting_id: str, transcript_text: str, segments: list[dict]) -> None:
    """Notes via Claude (with the meeting's template) + intelligence indexing +
    flagged moments + conflict detection."""
    db = get_db()
    row = db.execute(
        "SELECT title, attendees, template_id, markers, jot_notes FROM meetings WHERE id=?",
        (meeting_id,),
    ).fetchone()
    attendees = json.loads(row["attendees"]) if row else []
    markers = json.loads(row["markers"] or "[]") if row else []

    # Free plan: once this month's AI notes are used up, keep the transcript and
    # pause the notes. They can be written later (next month, or on Pro).
    if not license.can_write_ai_notes(meeting_id):
        db.execute("UPDATE meetings SET ai_paused=1 WHERE id=?", (meeting_id,))
        db.commit()
        from . import telemetry

        telemetry.emit("free_limit_reached")
        return

    generated = notes.generate_notes(
        meeting_id,
        row["title"] if row else "Meeting",
        transcript_text,
        attendees,
        template_id=row["template_id"] if row else None,
        jots=row["jot_notes"] if row else "",
    )
    content = generated["content"]

    flagged = _flagged_moments_section(markers, segments)
    if flagged:
        content = f"{content}\n\n{flagged}"
        from ..config import NOTES_DIR, write_secure_text

        write_secure_text(NOTES_DIR / f"{meeting_id}.md", content)

    sections = notes.split_sections(content)
    db.execute(
        "INSERT OR REPLACE INTO notes(meeting_id,content,sections,generated_at) "
        "VALUES(?,?,?,?)",
        (meeting_id, content, json.dumps(sections), now_iso()),
    )
    db.execute(
        "UPDATE meetings SET notes_path=?, ai_paused=0 WHERE id=?", (generated["path"], meeting_id)
    )
    db.commit()
    license.record_ai_notes(meeting_id)

    intelligence.index_notes(meeting_id, content)

    # Contradiction detection is best-effort — never fails the pipeline.
    try:
        from .conflicts import detect_conflicts

        detect_conflicts(meeting_id)
    except Exception:
        log.exception("Conflict detection failed for %s", meeting_id)


def _transcribe_fast(meeting_id: str, audio_path: Path) -> dict:
    """Uses the live incremental transcription recorder.py already produced
    during the call (see recorder._incremental_transcribe_loop) so only the
    short tail after the last covered block needs transcribing now, instead
    of re-running Whisper over the whole recording. Falls back to the old
    whole-file pass if there's no progress sidecar or anything about using
    it goes wrong."""
    progress_path = RECORDINGS_DIR / f"{meeting_id}.transcript_partial.json"
    try:
        if not progress_path.exists():
            return transcriber.transcribe(meeting_id, audio_path)

        progress = json.loads(progress_path.read_text())
        until = progress.get("transcribed_until", 0.0)
        prior_segments = progress.get("segments", [])

        with wave.open(str(audio_path), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()

        if until >= duration - 0.5:
            tail_segments: list[dict] = []
            language = None
        else:
            tail = transcriber.transcribe_tail(audio_path, until)
            tail_segments = tail["segments"]
            language = tail["language"]

        all_segments = prior_segments + tail_segments
        return transcriber.finish_from_segments(meeting_id, all_segments, language, duration)
    except Exception:
        log.exception(
            "Fast transcription path failed for %s — falling back to full pass", meeting_id
        )
        return transcriber.transcribe(meeting_id, audio_path)


def process_meeting(meeting_id: str, audio_path: Path) -> None:
    """Runs in a worker thread after recording stops."""
    db = get_db()
    try:
        db.execute(
            "UPDATE meetings SET ended_at=?, audio_path=? WHERE id=?",
            (now_iso(), str(audio_path), meeting_id),
        )
        db.commit()

        if _is_silent(audio_path):
            _set_status(
                meeting_id,
                "error",
                "No audio captured — check your input device in Settings → Recording.",
            )
            return

        _set_status(meeting_id, "transcribing")
        result = _transcribe_fast(meeting_id, audio_path)
        result = speakers.analyze(meeting_id, audio_path, result)
        # A user may delete this meeting during the local worker run. Do not
        # resurrect its transcript file or metadata after analysis completes.
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM meetings WHERE id=?', (meeting_id,)).fetchone():
            db.rollback()
            return
        write_secure_text(result["path"], result["text"])
        db.execute(
            "INSERT OR REPLACE INTO transcripts(meeting_id,text,language,duration_sec,segments,speaker_analysis) "
            "VALUES(?,?,?,?,?,?)",
            (
                meeting_id,
                result["text"],
                result["language"],
                result["duration_sec"],
                json.dumps(result["segments"]),
                json.dumps(result["speaker_analysis"]),
            ),
        )
        db.execute(
            "UPDATE meetings SET transcript_path=? WHERE id=?",
            (result["path"], meeting_id),
        )
        db.commit()

        _set_status(meeting_id, "generating")
        _generate_and_index(meeting_id, result["text"], result["segments"])
        _set_status(meeting_id, "ready")
    except Exception as exc:
        db.rollback()
        log.exception("Pipeline failed for meeting %s", meeting_id)
        _set_status(meeting_id, "error", _safe_error(exc))
    finally:
        (RECORDINGS_DIR / f"{meeting_id}.transcript_partial.json").unlink(missing_ok=True)
        close_db()  # worker thread exits here; don't leak its connection


def process_meeting_async(meeting_id: str, audio_path: Path) -> None:
    threading.Thread(
        target=process_meeting, args=(meeting_id, audio_path), daemon=True
    ).start()


def recover_interrupted() -> None:
    """Startup recovery. Meetings stuck mid-flight from a crashed session:
    - status 'recording' with spilled partial audio → salvage the audio and run
      the normal pipeline (the crash-loss fix — the meeting is NOT lost);
    - status 'transcribing'/'generating' with a finished WAV → re-run;
    - otherwise → mark error so the UI stops showing a phantom in-progress state.
    """
    from . import recorder as recorder_svc

    db = get_db()
    partials = set(recorder_svc.list_partial_meetings())
    stuck = db.execute(
        "SELECT id, status, audio_path FROM meetings "
        "WHERE status IN ('recording','transcribing','generating')"
    ).fetchall()
    for row in stuck:
        mid = row["id"]
        if row["status"] == "recording":
            salvaged = recorder_svc.finalize_partial(mid) if mid in partials else None
            partials.discard(mid)
            if salvaged is not None:
                log.info("Recovered interrupted recording %s", mid)
                db.execute("UPDATE meetings SET ended_at=? WHERE id=?", (now_iso(), mid))
                db.commit()
                process_meeting_async(mid, salvaged)
            else:
                _set_status(mid, "error", "Recording was interrupted before any audio was saved.")
        elif row["audio_path"] and Path(row["audio_path"]).exists():
            log.info("Re-running interrupted pipeline for %s", mid)
            process_meeting_async(mid, Path(row["audio_path"]))
        else:
            _set_status(mid, "error", "Processing was interrupted.")
    # Orphaned partial files with no matching stuck meeting: clean up quietly.
    for mid in partials:
        recorder_svc.finalize_partial(mid)


def regenerate_notes_async(meeting_id: str, template_id: str | None = None) -> None:
    """Re-run notes generation from the existing transcript, optionally with a
    different template."""

    def _run():
        db = get_db()
        try:
            t = db.execute(
                "SELECT text, segments FROM transcripts WHERE meeting_id=?",
                (meeting_id,),
            ).fetchone()
            if not t:
                raise RuntimeError("No transcript available for this meeting")
            if template_id is not None:
                db.execute(
                    "UPDATE meetings SET template_id=? WHERE id=?",
                    (template_id, meeting_id),
                )
                db.commit()
            _set_status(meeting_id, "generating")
            segments = json.loads(t["segments"] or "[]")
            _generate_and_index(meeting_id, t["text"], segments)
            _set_status(meeting_id, "ready")
        except Exception as exc:
            log.exception("Regenerate failed for %s", meeting_id)
            _set_status(meeting_id, "error", _safe_error(exc))
        finally:
            close_db()  # worker thread exits here; don't leak its connection

    threading.Thread(target=_run, daemon=True).start()
