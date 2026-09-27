"""Bounded session metadata; only the associated recording may accept names."""
import json
import hashlib
import sqlite3
import secrets
import threading
import time
from urllib.parse import urlparse
from ..db import get_db, get_setting
from .transcriber import apply_redaction


def call_key(url):
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if host == "meet.google.com":
        return "meet:" + parsed.path.strip("/").lower()
    if host == "zoom.us" or host.endswith(".zoom.us"):
        return "zoom:" + parsed.path.rstrip("/").split("/")[-1]
    return None


class SpeakerCapture:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.meeting_id = None
            self.nonce = secrets.token_urlsafe(32)
            self.expected = None
            self.candidates = {}
            self.sequence = 0
            self.last_time = -1
            self.last_observed = -1
            self.connections = {}

    def start(self, meeting_id, url=None):
        self.reset()
        with self.lock:
            self.meeting_id = meeting_id
            self.expected = call_key(url)

    def boundary(self):
        with self.lock:
            self.nonce = secrets.token_urlsafe(32)
            self.candidates.clear()
            self.last_time = -1
            self.last_observed = -1
            self.connections.clear()

    def connection_status(self):
        with self.lock:
            active = self.available()
            return {source: ('inactive' if not active else value[0] if time.time() - value[1] < 2 else 'disconnected')
                    for source in ('zoom', 'meet') for value in [self.connections.get(source, ('disconnected', 0))]}

    def available(self):
        from .recorder import recorder
        return bool(self.meeting_id and recorder.meeting_id == self.meeting_id and
                    get_setting("speaker_identification", True) and not recorder.paused and not recorder.muted)

    def offer(self, source, target, url=None):
        with self.lock:
            now = time.time()
            if not self.available():
                return {"collect": False, "now": now}
            key = (source, target)
            self.candidates = {k: v for k, v in self.candidates.items() if now - v["seen"] < 2}
            prior = self.candidates.get(key, {"since": now})
            matched = not self.expected or call_key(url) == self.expected
            self.candidates[key] = {"since": prior["since"], "seen": now, "matched": matched}
            unique = matched and len(self.candidates) == 1 and now - prior["since"] >= 1
            return {"collect": unique, "session": self.nonce, "now": now}

    def ingest(self, session, source, target, observed_at, participants, connection='connected'):
        from .recorder import recorder
        with self.lock:
            now = time.time()
            candidate = self.candidates.get((source, target))
            live = [v for v in self.candidates.values() if now - v["seen"] < 2]
            if not self.available() or not secrets.compare_digest(session, self.nonce):
                return False
            if not candidate or not candidate['matched'] or now - candidate["seen"] >= 2 or len(live) != 1:
                return False
            age = now - observed_at
            if not 0 <= age <= 0.75 or observed_at <= self.last_observed:
                return False
            audio_time = max(0, recorder.audio_elapsed - age)
            if audio_time <= self.last_time or self.sequence >= 100_000:
                return False
            cleaned = [{"id": hashlib.sha256(f'{self.meeting_id}:{target}:{p["id"]}'.encode()).hexdigest(), "name": apply_redaction(" ".join(p["name"].split()))} for p in participants]
            db = get_db()
            try:
                db.execute("INSERT INTO speaker_events(meeting_id,sequence,audio_time,source,participants,connection) VALUES(?,?,?,?,?,?)",
                           (self.meeting_id, self.sequence, audio_time, source, json.dumps(cleaned if connection == 'connected' else []), connection))
            except sqlite3.IntegrityError:
                db.rollback()  # meeting deleted while the source was connected
                return False
            db.commit()
            self.sequence += 1
            self.last_time = audio_time
            self.last_observed = observed_at
            self.connections[source] = (connection, now)
            return True


capture = SpeakerCapture()
