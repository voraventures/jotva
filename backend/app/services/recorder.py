"""Audio capture, cross-platform.

macOS:   microphone via sounddevice/CoreAudio + optional loopback device
         (BlackHole/aggregate) for system audio.
Windows: microphone via sounddevice/WASAPI + native WASAPI loopback of any
         output device via the `soundcard` package (no driver needed).

Capture chunks are spilled to disk continuously (raw float32 mono at the
device's native rate) so a crash, force-quit, or sleep mid-meeting cannot lose
the recording — only a bounded in-memory tail (~45s) is kept for the live
transcript, coach, and level meter. At stop time the spilled tracks are
resampled to 16 kHz mono and mixed in streaming blocks, so memory stays flat
regardless of meeting length. A sidecar {meeting_id}.partial.json describes the
in-progress tracks; startup recovery uses it to salvage interrupted meetings.
Output WAV is 0600 from creation.
"""
import json
import logging
import os
import sys
import threading
import wave
from pathlib import Path

import numpy as np

from ..config import RECORDINGS_DIR, secure_file, touch_secure
from ..events import hub

log = logging.getLogger("jotva.recorder")

TARGET_SR = 16000
IS_WINDOWS = sys.platform == "win32"

# In-memory tail kept per capture for live transcript (needs 15s), coach, and
# levels. Everything older is already on disk.
TAIL_SECONDS = 45
# How often the spiller thread flushes old chunks to disk.
SPILL_INTERVAL = 2.0

# Background full-quality transcription during the call, one block at a time,
# so only a short tail is left to transcribe at stop time (see
# _incremental_transcribe_loop). Audio is read straight from the in-memory
# chunks every INCR_INTERVAL seconds — well inside TAIL_SECONDS, so nothing is
# spilled to disk before it's read. 30s matches Whisper's own window and keeps
# the tail at stop to ~30s (about 2s of work at ~12x real time).
INCR_BLOCK_SEC = 30
# The first block is short so live notes (Pro) can start ~15 s after people
# start talking instead of waiting for a full 30 s block.
INCR_FIRST_BLOCK_SEC = 12
INCR_INTERVAL = 5.0

# Synthetic device indices >= WASAPI_BASE refer to Windows loopback captures.
WASAPI_BASE = 1000
_wasapi_devices: dict[int, str] = {}  # synthetic index -> soundcard mic id

try:
    import sounddevice as sd

    AUDIO_AVAILABLE = True
except Exception as exc:  # pragma: no cover - missing PortAudio
    sd = None
    AUDIO_AVAILABLE = False
    log.warning("sounddevice unavailable: %s", exc)

sc = None
if IS_WINDOWS:  # pragma: no cover - windows only
    try:
        import soundcard as sc  # WASAPI loopback
    except Exception as exc:
        log.warning("soundcard (WASAPI loopback) unavailable: %s", exc)


def _list_wasapi_loopbacks() -> list[dict]:
    """Windows: every output device exposed as a recordable loopback input."""
    if not (IS_WINDOWS and sc):
        return []
    out = []
    _wasapi_devices.clear()
    try:
        loopbacks = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    except Exception as exc:  # pragma: no cover
        log.warning("WASAPI loopback enumeration failed: %s", exc)
        return []
    for i, mic in enumerate(loopbacks):
        idx = WASAPI_BASE + i
        _wasapi_devices[idx] = str(mic.id)
        out.append(
            {
                "index": idx,
                "name": f"{mic.name} (loopback)",
                "channels": 2,
                "default_samplerate": 48000,
                "is_loopback_like": True,
            }
        )
    return out


def _is_loopback_like(name: str) -> bool:
    return any(
        k in name.lower() for k in ("blackhole", "loopback", "aggregate", "soundflower")
    )


def refresh_devices() -> None:
    """PortAudio snapshots the device list when it starts, so a mic plugged in
    (or reconnected, or made the macOS default) after launch stays invisible.
    Re-scan — but only while no stream is open, since re-initializing PortAudio
    would cut off a live recording or the presence watcher."""
    if not AUDIO_AVAILABLE:
        return
    from . import presence

    if recorder.is_recording or presence.watching():
        return
    try:
        sd._terminate()
        sd._initialize()
    except Exception as exc:
        log.warning("Could not refresh audio devices: %s", exc)


def saved_device(index: int | None, name: str | None) -> int | None:
    """Device indexes shift when devices come and go, so a saved choice is
    matched by name. If that device is gone, use the system default (None)."""
    if not name:
        return index
    for dev in list_input_devices():
        if dev["name"] == name:
            return dev["index"]
    log.warning("Saved input device %r is not connected; using the system default", name)
    return None


def list_input_devices() -> list[dict]:
    devices = []
    if AUDIO_AVAILABLE:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append(
                    {
                        "index": idx,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "default_samplerate": dev["default_samplerate"],
                        "is_loopback_like": _is_loopback_like(dev["name"]),
                    }
                )
    devices.extend(_list_wasapi_loopbacks())
    return devices


def default_input_status() -> dict:
    """What device 'System default' actually resolves to right now, so the UI
    can warn if it's a virtual/loopback device instead of a real mic — the
    cause of silent recordings when nothing is routed into that device."""
    if not AUDIO_AVAILABLE:
        return {"name": None, "is_loopback_like": False}
    try:
        idx = sd.default.device[0]
        info = sd.query_devices(idx, "input")
        return {"name": info["name"], "is_loopback_like": _is_loopback_like(info["name"])}
    except Exception:
        return {"name": None, "is_loopback_like": False}


def _resolve_mic_device(requested: int | None) -> int | None:
    """Pick the mic capture device. An explicit user choice is always honored
    (even a virtual device — that may be deliberate). When nothing is chosen,
    don't silently record from a virtual loopback device that happens to be
    the OS default input (e.g. BlackHole with nothing routed into it, which
    produces a real-looking but completely silent recording) — fall back to
    the first real microphone instead."""
    if requested is not None or not AUDIO_AVAILABLE:
        return requested
    default = default_input_status()
    if not default["is_loopback_like"]:
        return None  # real default mic — keep using sounddevice's own default
    for dev in list_input_devices():
        if not dev["is_loopback_like"]:
            log.warning(
                "System default input %r is a virtual/loopback device; "
                "falling back to real microphone %r",
                default["name"],
                dev["name"],
            )
            return dev["index"]
    raise RuntimeError(
        "No microphone found. Plug in or connect a microphone, or choose one in "
        "Jotva → Settings → Recording. (The Mac's current input is a virtual "
        "device such as BlackHole, which Jotva won't record from.)"
    )


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim > 1:
        return audio.mean(axis=1)
    return audio


class _SpillCapture:
    """Shared chunk-buffer + disk-spill behavior for both capture kinds.

    `chunks` holds the recent tail; older chunks are appended (as float32 mono
    at native samplerate) to `spill_path`. `base_index` counts chunks already
    spilled, so absolute chunk cursors (coach) survive pruning.
    """

    def __init__(self):
        self.chunks: list[np.ndarray] = []
        self.samplerate = TARGET_SR
        self.base_index = 0
        self.total_frames = 0
        self.lock = threading.Lock()
        self.spill_path: Path | None = None
        self._spill_file = None

    def open_spill(self, path: Path) -> None:
        self.spill_path = path
        touch_secure(path)
        self._spill_file = open(path, "ab")

    def spill_old_chunks(self) -> None:
        """Move chunks beyond the in-memory tail out to disk."""
        if self._spill_file is None:
            return
        tail_frames = int(TAIL_SECONDS * self.samplerate)
        with self.lock:
            total = sum(len(c) for c in self.chunks)
            take = 0
            while take < len(self.chunks) and total - len(self.chunks[take]) > tail_frames:
                total -= len(self.chunks[take])
                take += 1
            to_write = self.chunks[:take]
            del self.chunks[:take]
            self.base_index += take
        for chunk in to_write:
            _to_mono(chunk).astype(np.float32).tofile(self._spill_file)
        # Flush so the incremental transcriber (a separate reader of this same
        # path) never sees a shorter file than what spill_old_chunks has
        # already committed to move out of memory.
        self._spill_file.flush()

    def close_spill(self) -> None:
        """Flush every remaining chunk to disk and close the file."""
        if self._spill_file is None:
            return
        with self.lock:
            remaining = self.chunks
            self.chunks = []
            self.base_index += len(remaining)
        for chunk in remaining:
            _to_mono(chunk).astype(np.float32).tofile(self._spill_file)
        self._spill_file.flush()
        self._spill_file.close()
        self._spill_file = None


class _DeviceCapture(_SpillCapture):
    def __init__(self, device_index: int | None):
        super().__init__()
        self.device_index = device_index
        self.stream = None

    def start(self):
        info = sd.query_devices(self.device_index, "input")
        self.samplerate = int(info["default_samplerate"])
        channels = min(2, max(1, info["max_input_channels"]))

        def callback(indata, frames, time_info, status):
            if recorder.paused:
                return  # paused: drop frames entirely, the timeline stops
            self.total_frames += frames
            if recorder.muted:
                # privacy mute zone: keep the timeline, drop the content
                self.chunks.append(np.zeros_like(indata))
            else:
                self.chunks.append(indata.copy())

        self.stream = sd.InputStream(
            device=self.device_index,
            channels=channels,
            samplerate=self.samplerate,
            dtype="float32",
            callback=callback,
        )
        self.stream.start()

    def stop(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()


class _WasapiLoopbackCapture(_SpillCapture):
    """Windows system-audio capture through soundcard's WASAPI loopback."""

    def __init__(self, synthetic_index: int):
        super().__init__()
        if synthetic_index not in _wasapi_devices:
            _list_wasapi_loopbacks()  # refresh mapping (device list may be stale)
        mic_id = _wasapi_devices.get(synthetic_index)
        if mic_id is None or sc is None:
            raise RuntimeError(
                "System audio device not found — re-select it in Settings → Recording"
            )
        self._mic = sc.get_microphone(mic_id, include_loopback=True)
        self.samplerate = 48000
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        def run():
            try:
                with self._mic.recorder(samplerate=self.samplerate, channels=2) as rec:
                    while not self._stop.is_set():
                        data = rec.record(numframes=self.samplerate // 10)
                        if recorder.paused:
                            continue
                        self.total_frames += len(data)
                        self.chunks.append(np.zeros_like(data) if recorder.muted else np.asarray(data, dtype=np.float32))
            except Exception as exc:  # pragma: no cover
                log.error("WASAPI loopback capture failed: %s", exc)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


def _make_capture(device_index: int | None):
    if device_index is not None and device_index >= WASAPI_BASE:
        return _WasapiLoopbackCapture(device_index)
    return _DeviceCapture(device_index)


def _resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or len(audio) == 0:
        return audio
    duration = len(audio) / src_sr
    n_out = int(duration * dst_sr)
    x_old = np.linspace(0, duration, num=len(audio), endpoint=False)
    x_new = np.linspace(0, duration, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _sidecar_path(meeting_id: str) -> Path:
    return RECORDINGS_DIR / f"{meeting_id}.partial.json"


def _drain_capture(cap, cursor: dict) -> np.ndarray | None:
    """New audio (16 kHz mono float32) from one capture since `cursor`, an
    absolute chunk index that survives spilling. None if some of that audio
    was already spilled to disk, i.e. the reader fell behind."""
    with cap.lock:
        start_abs = cursor.get("chunk_index", 0)
        if start_abs < cap.base_index:
            return None
        chunks = list(cap.chunks[start_abs - cap.base_index:])
        cursor["chunk_index"] = cap.base_index + len(cap.chunks)
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    audio = np.concatenate([_to_mono(c) for c in chunks], axis=0).astype(np.float32)
    return _resample(audio, cap.samplerate, TARGET_SR).astype(np.float32)


def _load_tracks(track_specs: list[dict]) -> list[dict]:
    """Stats each raw float32-mono track file fresh (sizes grow during an
    active recording), dropping any that don't exist yet or are empty."""
    tracks = []
    for spec in track_specs:
        p = Path(spec["path"])
        if not p.exists():
            continue
        n = p.stat().st_size // 4  # float32
        if n > 0:
            tracks.append({"path": p, "sr": int(spec["samplerate"]), "n": n})
    return tracks


def _mix_window(tracks: list[dict], t0: float, t1: float) -> np.ndarray:
    """Mixes all tracks over [t0, t1) seconds into 16 kHz mono float32,
    resampling each track's native rate on the fly. Shared by the final WAV
    assembly and the live incremental transcriber, so both see identical
    audio content for the same time range."""
    out_len = int(round((t1 - t0) * TARGET_SR))
    if out_len <= 0:
        return np.zeros(0, dtype=np.float32)
    mixed = np.zeros(out_len, dtype=np.float32)
    x_out = t0 + np.arange(out_len) / TARGET_SR
    for t in tracks:
        src_start = max(0, int(t0 * t["sr"]) - 1)
        src_end = min(t["n"], int(np.ceil(t1 * t["sr"])) + 1)
        if src_end <= src_start:
            continue
        seg = np.fromfile(
            t["path"], dtype=np.float32, count=src_end - src_start, offset=src_start * 4
        )
        x_src = (src_start + np.arange(len(seg))) / t["sr"]
        mixed += np.interp(x_out, x_src, seg, left=0.0, right=0.0).astype(np.float32)
    return mixed


def mix_tracks_to_wav(track_specs: list[dict], out_path: Path) -> Path:
    """Mix raw float32-mono track files (each {path, samplerate}) into a 16 kHz
    mono int16 WAV, streaming in 60-second blocks so memory stays flat for
    arbitrarily long meetings. Two passes: peak scan, then scaled write."""
    tracks = _load_tracks(track_specs)

    block_sec = 60
    if tracks:
        duration = max(t["n"] / t["sr"] for t in tracks)
    else:
        duration = 1.0  # 1s silence placeholder

    n_blocks = max(1, int(np.ceil(duration / block_sec)))
    peak = 0.0
    for i in range(n_blocks):
        block = _mix_window(tracks, i * block_sec, min(duration, (i + 1) * block_sec))
        if len(block):
            peak = max(peak, float(np.max(np.abs(block))))
    scale = 1.0 / peak if peak > 1.0 else 1.0

    touch_secure(out_path)  # 0600 before any audio bytes land (C5)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_SR)
        for i in range(n_blocks):
            block = _mix_window(tracks, i * block_sec, min(duration, (i + 1) * block_sec)) * scale
            wf.writeframes((block * 32767).astype(np.int16).tobytes())
    secure_file(out_path)
    return out_path


def _transcript_progress_path(meeting_id: str) -> Path:
    return RECORDINGS_DIR / f"{meeting_id}.transcript_partial.json"


def _write_transcript_progress(meeting_id: str, until: float, segments: list[dict]) -> None:
    """Atomically persists live-transcription progress so the pipeline can
    pick it up after stop (and, for a crashed session, recovery can too)."""
    path = _transcript_progress_path(meeting_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"transcribed_until": until, "segments": segments}))
    secure_file(tmp)
    os.replace(tmp, path)


def finalize_partial(meeting_id: str) -> Path | None:
    """Startup recovery: mix whatever a crashed session managed to spill to disk
    into the final WAV, then clean up the partial files. Returns the WAV path,
    or None if there is nothing to salvage."""
    sidecar = _sidecar_path(meeting_id)
    if not sidecar.exists():
        return None
    try:
        meta = json.loads(sidecar.read_text())
        specs = [s for s in meta.get("captures", []) if Path(s["path"]).exists()]
        if not any(Path(s["path"]).stat().st_size >= 4 for s in specs):
            _cleanup_partial(meeting_id, meta)
            return None
        path = RECORDINGS_DIR / f"{meeting_id}.wav"
        mix_tracks_to_wav(specs, path)
        _cleanup_partial(meeting_id, meta)
        return path
    except Exception:
        log.exception("Could not salvage partial recording for %s", meeting_id)
        return None


def list_partial_meetings() -> list[str]:
    return [p.name.removesuffix(".partial.json") for p in RECORDINGS_DIR.glob("*.partial.json")]


def _cleanup_partial(meeting_id: str, meta: dict) -> None:
    for spec in meta.get("captures", []):
        Path(spec["path"]).unlink(missing_ok=True)
    _sidecar_path(meeting_id).unlink(missing_ok=True)


class Recorder:
    """Singleton recorder managing one active recording at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._captures: list[_SpillCapture] = []
        self._meeting_id: str | None = None
        self._level_thread: threading.Thread | None = None
        self._live_transcript_thread: threading.Thread | None = None
        self._spill_thread: threading.Thread | None = None
        self._incr_thread: threading.Thread | None = None
        self._stop_levels = threading.Event()
        self._started_at: float | None = None
        self.muted = False           # privacy mute zone: capture writes silence
        self.paused = False          # paused: captures drop frames entirely
        self.markers: list[float] = []  # flagged moments, seconds from start
        # Background full-quality transcription progress (see
        # _incremental_transcribe_loop) — read/written under _live_lock.
        self._live_lock = threading.Lock()
        self._live_segments: list[dict] = []
        self._live_transcribed_until: float = 0.0

    @property
    def elapsed(self) -> float:
        import time

        return time.monotonic() - self._started_at if self._started_at else 0.0

    @property
    def audio_elapsed(self) -> float:
        return max((cap.total_frames / cap.samplerate for cap in self._captures), default=0.0)

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        from .speaker_capture import capture
        capture.boundary()
        hub.emit("recording_muted", {"muted": muted})

    # UI elapsed time stays wall-clock; markers/attribution use saved frames.
    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        from .speaker_capture import capture
        capture.boundary()
        hub.emit("recording_paused", {"paused": paused})

    def add_marker(self) -> float | None:
        if self._meeting_id is None:
            return None
        t = self.audio_elapsed
        self.markers.append(round(t, 1))
        hub.emit("marker_added", {"at": round(t, 1), "count": len(self.markers)})
        return t

    def drain_for_coach(self, cursor: dict) -> np.ndarray:
        """Return new 16k mono audio (mic capture only) since the last call.
        cursor is caller-owned state: {"chunk_index": int} — an absolute index
        that stays valid as old chunks are spilled to disk."""
        if not self._captures:
            return np.zeros(0, dtype=np.float32)
        cap = self._captures[0]
        with cap.lock:
            start_abs = cursor.get("chunk_index", 0)
            start_rel = max(0, start_abs - cap.base_index)
            chunks = list(cap.chunks[start_rel:])
            cursor["chunk_index"] = cap.base_index + len(cap.chunks)
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate([_to_mono(c) for c in chunks], axis=0)
        return _resample(audio, cap.samplerate, TARGET_SR)

    @property
    def is_recording(self) -> bool:
        return self._meeting_id is not None

    @property
    def meeting_id(self) -> str | None:
        return self._meeting_id

    def start(self, meeting_id: str, mic_device: int | None, system_device: int | None) -> None:
        if not AUDIO_AVAILABLE:
            raise RuntimeError("Audio capture is unavailable on this system")
        with self._lock:
            if self._meeting_id is not None:
                raise RuntimeError("A recording is already in progress")
            self._captures = []
            try:
                mic_device = _resolve_mic_device(mic_device)
                mic = _make_capture(mic_device)
                mic.start()
                self._captures.append(mic)
                if system_device is not None and system_device != mic_device:
                    sys_cap = _make_capture(system_device)
                    sys_cap.start()
                    self._captures.append(sys_cap)
            except Exception:
                for c in self._captures:
                    try:
                        c.stop()
                    except Exception:
                        pass
                self._captures = []
                raise

            # Crash-safety: open spill files + sidecar before declaring started.
            specs = []
            for i, cap in enumerate(self._captures):
                spill = RECORDINGS_DIR / f"{meeting_id}.cap{i}.f32raw"
                cap.open_spill(spill)
                specs.append({"path": str(spill), "samplerate": cap.samplerate})
            sidecar = _sidecar_path(meeting_id)
            sidecar.write_text(json.dumps({"meeting_id": meeting_id, "captures": specs}))
            secure_file(sidecar)

            self._meeting_id = meeting_id
            import time

            self._started_at = time.monotonic()
            self.muted = False
            self.paused = False
            self.markers = []
            self._live_segments = []
            self._live_transcribed_until = 0.0
            self._stop_levels.clear()
            self._level_thread = threading.Thread(target=self._emit_levels, daemon=True)
            self._level_thread.start()
            self._live_transcript_thread = threading.Thread(
                target=self._emit_live_transcript, daemon=True
            )
            self._live_transcript_thread.start()
            self._spill_thread = threading.Thread(target=self._spill_loop, daemon=True)
            self._spill_thread.start()
            self._incr_thread = threading.Thread(
                target=self._incremental_transcribe_loop, args=(meeting_id,), daemon=True
            )
            self._incr_thread.start()
            hub.emit("recording_started", {"meeting_id": meeting_id})

    def _spill_loop(self):
        """Continuously move audio older than the in-memory tail to disk."""
        while not self._stop_levels.wait(SPILL_INTERVAL):
            for cap in list(self._captures):
                try:
                    cap.spill_old_chunks()
                except Exception:
                    log.exception("Audio spill failed")

    def _emit_levels(self):
        """Emit RMS levels ~4x/sec so the UI waveform animates with real audio."""
        while not self._stop_levels.wait(0.25):
            try:
                cap = self._captures[0] if self._captures else None
                if cap and cap.chunks:
                    recent = cap.chunks[-1]
                    rms = float(np.sqrt(np.mean(np.square(recent))))
                    hub.emit("recording_level", {"rms": min(1.0, rms * 8)})
            except Exception:
                pass

    def _emit_live_transcript(self):
        """Every 10s take the last 15s of audio and run tiny-model transcription.
        Emits transcript_chunk events for the live preview display."""
        from . import transcriber as transcriber_svc
        INTERVAL = 10.0
        WINDOW_SEC = 15
        while not self._stop_levels.wait(INTERVAL):
            try:
                cap = self._captures[0] if self._captures else None
                if cap is None:
                    continue
                with cap.lock:
                    # Only the in-memory tail is needed: it always covers ≥15s.
                    frames_needed = int(WINDOW_SEC * cap.samplerate)
                    got, take = 0, 0
                    for chunk in reversed(cap.chunks):
                        got += len(chunk)
                        take += 1
                        if got >= frames_needed:
                            break
                    recent = list(cap.chunks[len(cap.chunks) - take:]) if take else []
                if not recent:
                    continue
                window = np.concatenate([_to_mono(c) for c in recent], axis=0)[-frames_needed:]
                if len(window) < cap.samplerate:  # less than 1 second
                    continue
                resampled = _resample(window, cap.samplerate, TARGET_SR)
                text = transcriber_svc.transcribe_chunk(resampled)
                if text:
                    hub.emit("transcript_chunk", {"text": text, "is_partial": True})
            except Exception as exc:
                log.debug("Live transcript emit failed: %s", exc)

    def _incremental_transcribe_loop(self, meeting_id: str) -> None:
        """Transcribes the meeting with the real (accuracy) model in the
        background, one INCR_BLOCK_SEC block at a time, while the meeting is
        still going. At stop time the pipeline only has to transcribe the
        short remaining tail (see pipeline._transcribe_fast) — this is what
        makes notes appear seconds after stop.

        Each pass drains new in-memory chunks from every capture (own cursors,
        independent of the coach's), resamples to 16 kHz and mixes them the
        way _mix_window does. If a pass ever falls so far behind that chunks
        were already spilled to disk, it stops and leaves the rest to the
        stop-time pipeline rather than risk a gap in the transcript."""
        from . import transcriber as transcriber_svc

        captures = list(self._captures)
        cursors = [{"chunk_index": 0} for _ in captures]
        pending = [np.zeros(0, dtype=np.float32) for _ in captures]
        buf = np.zeros(0, dtype=np.float32)
        with self._live_lock:
            until = self._live_transcribed_until
        while not self._stop_levels.wait(INCR_INTERVAL):
            try:
                for i, cap in enumerate(captures):
                    new = _drain_capture(cap, cursors[i])
                    if new is None:
                        log.warning("Live transcription fell behind; the rest is transcribed at stop")
                        return
                    pending[i] = np.concatenate([pending[i], new])
                n = min(len(p) for p in pending) if pending else 0
                if n:
                    buf = np.concatenate([buf, np.sum([p[:n] for p in pending], axis=0)])
                    pending = [p[n:] for p in pending]
                while not self._stop_levels.is_set():
                    block_sec = INCR_FIRST_BLOCK_SEC if until == 0 else INCR_BLOCK_SEC
                    block = block_sec * TARGET_SR
                    if len(buf) < block:
                        break
                    segs = transcriber_svc.transcribe_array(buf[:block], offset=until)
                    buf = buf[block:]
                    until += block_sec
                    with self._live_lock:
                        self._live_segments.extend(segs)
                        self._live_transcribed_until = until
                        snapshot = list(self._live_segments)
                    _write_transcript_progress(meeting_id, until, snapshot)
            except Exception:
                log.exception("Incremental transcription failed")

    def stop(self) -> Path:
        from .speaker_capture import capture
        capture.reset()
        with self._lock:
            if self._meeting_id is None:
                raise RuntimeError("No recording in progress")
            meeting_id = self._meeting_id
            self._stop_levels.set()
            captures = self._captures
            for c in captures:
                try:
                    c.stop()
                except Exception:
                    log.exception("Capture stop failed")
            self._captures = []
            self._meeting_id = None
            self._started_at = None
            self.muted = False
            self.paused = False

        specs = []
        for cap in captures:
            try:
                cap.close_spill()
            except Exception:
                log.exception("Spill finalize failed")
            if cap.spill_path is not None:
                specs.append({"path": str(cap.spill_path), "samplerate": cap.samplerate})

        path = RECORDINGS_DIR / f"{meeting_id}.wav"
        mix_tracks_to_wav(specs, path)
        _cleanup_partial(meeting_id, {"captures": specs})
        hub.emit("recording_stopped", {"meeting_id": meeting_id, "path": str(path)})
        return path


recorder = Recorder()
