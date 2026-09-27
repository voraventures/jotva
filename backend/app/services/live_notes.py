"""Live notes (Pro): while a meeting is recording, the AI keeps a short set of
running notes (key points, decisions, action items) up to date.

Every INTERVAL seconds it takes the transcript written since the last update
(the recorder's 30-second live blocks) and asks the AI to fold it into the
current notes. Sending only the new part keeps each call small. The final,
polished notes are still written from the whole meeting after Stop.
"""
import logging
import threading
import time

from ..events import hub
from . import license, notes
from .recorder import recorder

log = logging.getLogger("jotva.live_notes")

INTERVAL = 90.0        # seconds between updates
MIN_NEW_CHARS = 250    # skip an update when little new was said
MAX_UPDATES = 60       # hard cap per meeting (~90 min of updates)


class LiveNotes:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.meeting_id: str | None = None
        self.text = ""

    def start(self, meeting_id: str) -> bool:
        """Starts for Pro users who haven't turned live notes off."""
        self.stop()
        from ..db import get_setting

        if not license.has_feature("live_notes") or get_setting("live_notes_enabled", True) is False:
            return False
        self._stop.clear()
        self.meeting_id, self.text = meeting_id, ""
        self._thread = threading.Thread(target=self._run, args=(meeting_id,), daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)  # an in-flight AI call finishes in the background
            self._thread = None

    def _new_transcript(self, seen: int) -> tuple[str, int]:
        with recorder._live_lock:
            segments = list(recorder._live_segments)
        return " ".join(s.get("text", "").strip() for s in segments[seen:]).strip(), len(segments)

    def _run(self, meeting_id: str) -> None:
        seen = updates = 0
        started = time.monotonic()
        while not self._stop.wait(INTERVAL) and updates < MAX_UPDATES:
            new, count = self._new_transcript(seen)
            if len(new) < MIN_NEW_CHARS:
                continue
            try:
                text = notes.live_update(self.text, new, minutes_in=int((time.monotonic() - started) / 60))
            except Exception as exc:  # never disturb the recording
                log.warning("Live notes update failed: %s", exc)
                continue
            if self._stop.is_set() or not text:
                return
            seen, updates, self.text = count, updates + 1, text
            hub.emit("live_notes", {"meeting_id": meeting_id, "text": text, "at": time.time()})


live_notes = LiveNotes()
