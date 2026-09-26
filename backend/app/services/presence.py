"""Join-triggered auto-record. After the user clicks Join on an upcoming
calendar meeting, watch live audio levels for sustained talking and then hand
off to the same meeting_prompt / auto_record_starting flow the calendar-clock
check in calendars/sync.py already drives. Only per-second RMS scalars are
kept in memory — no audio is buffered or written before a recording is
actually started."""
import json
import logging
import threading
import time
from collections import deque

import numpy as np

from ..db import close_db, get_db, get_setting
from ..events import hub
from . import recorder as recorder_svc
from .calendars import sync as cal_sync

log = logging.getLogger("jotva.presence")

# Initial estimates — tune from real calls. Raw float RMS of the input stream;
# recorder._emit_levels scales this by 8 for the UI meter, so 0.015 ≈ 12% on
# the meter, comfortably above room noise but well under normal speech.
TALK_RMS_THRESHOLD = 0.015
SUSTAIN_WINDOW_SEC = 8
SUSTAIN_REQUIRED_SEC = 4
WATCH_TIMEOUT_SEC = 20 * 60
POLL_SEC = 1.0

_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_watching_event_id: str | None = None


def _rms_stream(device: int):
    import sounddevice as sd

    info = sd.query_devices(device, "input")
    box = {"rms": 0.0}

    def callback(indata, frames, time_info, status):
        box["rms"] = float(np.sqrt(np.mean(np.square(indata))))

    stream = sd.InputStream(
        device=device,
        channels=min(2, max(1, info["max_input_channels"])),
        samplerate=int(info["default_samplerate"]),
        dtype="float32",
        callback=callback,
    )
    stream.start()
    return stream.close, box


def _rms_wasapi(synthetic_index: int):
    if synthetic_index not in recorder_svc._wasapi_devices:
        recorder_svc._list_wasapi_loopbacks()
    mic_id = recorder_svc._wasapi_devices.get(synthetic_index)
    if mic_id is None or recorder_svc.sc is None:
        raise RuntimeError("Loopback device not found")
    mic = recorder_svc.sc.get_microphone(mic_id, include_loopback=True)
    box = {"rms": 0.0}
    stop = threading.Event()

    def run():
        try:
            with mic.recorder(samplerate=48000, channels=2) as rec:
                while not stop.is_set():
                    data = rec.record(numframes=4800)
                    box["rms"] = float(np.sqrt(np.mean(np.square(data))))
        except Exception as exc:
            log.warning("Presence loopback watch failed: %s", exc)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def close():
        stop.set()
        t.join(timeout=3)

    return close, box


def _open_sources() -> list[tuple]:
    sources = []
    try:
        mic = recorder_svc._resolve_mic_device(get_setting("mic_device"))
        if mic is not None:
            sources.append(_rms_stream(mic))
    except Exception as exc:
        log.warning("Presence watch: mic unavailable: %s", exc)

    system = get_setting("system_device")
    if system is not None:
        try:
            if system >= recorder_svc.WASAPI_BASE:
                sources.append(_rms_wasapi(system))
            else:
                sources.append(_rms_stream(system))
        except Exception as exc:
            log.warning("Presence watch: system audio unavailable: %s", exc)
    return sources


def _fire_prompt(event_id: str) -> None:
    """Same guards and payload as sync._check_auto_record, so RecordPrompt.jsx
    handles the result identically whether the trigger was the clock or talk."""
    mode = get_setting("recording_mode", "confirm_30s")
    if mode in ("manual", "off"):
        return
    from . import license

    if mode == "all" and not license.has_feature("auto_record"):
        mode = "confirm_30s"  # free plan: ask instead of auto-starting
    db = get_db()
    row = db.execute(
        "SELECT * FROM calendar_events WHERE id=? AND cancelled=0 AND prompted=0 "
        "AND recorded_meeting_id IS NULL",
        (event_id,),
    ).fetchone()
    if not row or cal_sync._is_excluded(row["title"]):
        return
    db.execute("UPDATE calendar_events SET prompted=1 WHERE id=?", (event_id,))
    db.commit()
    payload = {
        "event_id": row["id"],
        "title": row["title"],
        "start": row["start"],
        "attendees": json.loads(row["attendees"] or "[]"),
        "seconds_until_start": 0,
        "mode": mode,
        "trigger": "talk_detected",
    }
    log.info("Talk detected for %s — prompting (mode=%s)", event_id, mode)
    hub.emit("auto_record_starting" if mode == "all" else "meeting_prompt", payload)


def _still_wanted(event_id: str) -> bool:
    if recorder_svc.recorder.is_recording:
        return False
    row = get_db().execute(
        "SELECT cancelled, prompted, recorded_meeting_id FROM calendar_events WHERE id=?",
        (event_id,),
    ).fetchone()
    return bool(row) and not (row["cancelled"] or row["prompted"] or row["recorded_meeting_id"])


def _run(event_id: str) -> None:
    sources: list[tuple] = []
    try:
        sources = _open_sources()
        if not sources:
            log.warning("Presence watch for %s: no audio source available", event_id)
            return
        recent: deque[bool] = deque(maxlen=SUSTAIN_WINDOW_SEC)
        started = time.monotonic()
        while not _stop.wait(POLL_SEC):
            if not _still_wanted(event_id):
                return
            if time.monotonic() - started > WATCH_TIMEOUT_SEC:
                log.info("Presence watch for %s timed out", event_id)
                return
            level = max(box["rms"] for _close, box in sources)
            recent.append(level > TALK_RMS_THRESHOLD)
            if len(recent) == SUSTAIN_WINDOW_SEC and sum(recent) >= SUSTAIN_REQUIRED_SEC:
                _fire_prompt(event_id)
                return
    except Exception:
        log.exception("Presence watch for %s crashed", event_id)
    finally:
        for close, _box in sources:
            try:
                close()
            except Exception:
                pass
        close_db()


def start_watch(event_id: str) -> bool:
    """Returns False when watching isn't possible (audio libs missing) or
    pointless (auto-record disabled); the caller still opens the join link."""
    global _thread, _watching_event_id
    if not recorder_svc.AUDIO_AVAILABLE:
        return False
    if get_setting("recording_mode", "confirm_30s") in ("manual", "off"):
        return False
    with _lock:
        _stop_locked()
        _stop.clear()
        _watching_event_id = event_id
        _thread = threading.Thread(target=_run, args=(event_id,), daemon=True)
        _thread.start()
    return True


def _stop_locked() -> None:
    global _thread, _watching_event_id
    _stop.set()
    if _thread is not None and _thread is not threading.current_thread():
        _thread.join(timeout=5)
    _thread = None
    _watching_event_id = None


def stop_watch() -> None:
    with _lock:
        _stop_locked()


def watching() -> str | None:
    return _watching_event_id if _thread is not None and _thread.is_alive() else None
