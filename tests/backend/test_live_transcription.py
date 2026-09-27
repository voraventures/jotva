"""Live (during-the-call) transcription reads audio straight from memory in
30-second blocks, so only a short tail is left at stop. Fake captures and a fake
transcriber: no microphone, no Whisper model."""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-live-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import numpy as np
from app.services import recorder, transcriber


class FakeCapture:
    def __init__(self, samplerate):
        self.samplerate = samplerate
        self.chunks, self.base_index, self.lock = [], 0, threading.Lock()

    def feed(self, seconds):
        with self.lock:
            self.chunks.append(np.full(int(seconds * self.samplerate), 0.1, dtype=np.float32))


def make_recorder(captures):
    rec = object.__new__(recorder.Recorder)
    rec._captures = captures
    rec._stop_levels = threading.Event()
    rec._live_lock = threading.Lock()
    rec._live_segments, rec._live_transcribed_until = [], 0.0
    return rec


def run_loop(monkeypatch, captures, feed):
    blocks, progress = [], []
    monkeypatch.setattr(recorder, "INCR_INTERVAL", 0.01)
    monkeypatch.setattr(transcriber, "transcribe_array",
                        lambda audio, offset: blocks.append((offset, len(audio))) or [{"start": offset, "text": "x"}])
    monkeypatch.setattr(recorder, "_write_transcript_progress", lambda mid, until, segs: progress.append(until))
    rec = make_recorder(captures)
    t = threading.Thread(target=rec._incremental_transcribe_loop, args=("m1",))
    t.start()
    feed()
    time.sleep(0.2)
    rec._stop_levels.set()
    t.join(2)
    return blocks, progress, rec


def test_transcribes_30s_blocks_from_memory_with_correct_offsets(monkeypatch):
    mic, system = FakeCapture(44100), FakeCapture(48000)  # different native rates get mixed
    def feed():
        for _ in range(14):  # 70 s of audio, 5 s at a time
            mic.feed(5); system.feed(5); time.sleep(0.01)
    blocks, progress, rec = run_loop(monkeypatch, [mic, system], feed)
    assert [b[0] for b in blocks] == [0, 30]
    assert all(abs(b[1] - 30 * 16000) <= 1 for b in blocks)
    assert progress == [30, 60] and rec._live_transcribed_until == 60  # a ~10 s tail is left for stop


def test_stops_safely_if_audio_was_spilled_before_it_was_read():
    cap = FakeCapture(16000)
    cap.base_index = 3  # three chunks already went to disk
    assert recorder._drain_capture(cap, {"chunk_index": 0}) is None
    cap.feed(1)
    cursor = {"chunk_index": 3}
    assert len(recorder._drain_capture(cap, cursor)) == 16000 and cursor["chunk_index"] == 4
