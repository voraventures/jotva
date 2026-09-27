"""SQLite persistence. DB file is chmod 600 on creation (C5)."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import DB_PATH, secure_file, touch_secure

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Untitled meeting',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'recording', -- recording|transcribing|generating|ready|error
    audio_path TEXT,
    transcript_path TEXT,
    notes_path TEXT,
    attendees TEXT NOT NULL DEFAULT '[]',     -- JSON array of names
    calendar_event_id TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS transcripts (
    meeting_id TEXT PRIMARY KEY REFERENCES meetings(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    language TEXT,
    duration_sec REAL
);
CREATE TABLE IF NOT EXISTS speaker_events (
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    audio_time REAL NOT NULL,
    source TEXT NOT NULL,
    participants TEXT NOT NULL,
    PRIMARY KEY(meeting_id, sequence)
);
CREATE TABLE IF NOT EXISTS notes (
    meeting_id TEXT PRIMARY KEY REFERENCES meetings(id) ON DELETE CASCADE,
    content TEXT NOT NULL,                    -- full markdown
    sections TEXT NOT NULL DEFAULT '{}',      -- JSON {section_key: markdown}
    generated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    owner TEXT NOT NULL DEFAULT 'TBD',
    action TEXT NOT NULL,
    due TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open'       -- open|done
);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,                      -- dedup key: norm_title|start
    provider TEXT NOT NULL,                   -- google|microsoft|apple
    provider_ids TEXT NOT NULL DEFAULT '[]',  -- JSON list of provider event ids merged in
    title TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT,
    attendees TEXT NOT NULL DEFAULT '[]',
    cancelled INTEGER NOT NULL DEFAULT 0,
    recorded_meeting_id TEXT,
    prompted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,                       -- the template-specific sections spec
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    new_decision TEXT NOT NULL,
    old_decision TEXT NOT NULL,
    old_meeting_id TEXT,
    old_meeting_title TEXT,
    old_date TEXT,
    explanation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',      -- open|superseded|reviewed
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shares (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    owner_install_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    install_id TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    joined_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, install_id)
);
CREATE TABLE IF NOT EXISTS mobile_sessions (
    id TEXT PRIMARY KEY,
    mobile_token TEXT NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    device_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ai_note_usage (
    meeting_id TEXT PRIMARY KEY,
    month TEXT NOT NULL,              -- YYYY-MM the bundled-AI notes were first written
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_accounts (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,            -- gmail | icloud | imap | microsoft
    address TEXT NOT NULL,
    host TEXT, port INTEGER, username TEXT,
    created_at TEXT NOT NULL,
    last_sync TEXT, last_error TEXT,
    state TEXT NOT NULL DEFAULT '{}'   -- per-folder sync cursors (JSON)
);
CREATE TABLE IF NOT EXISTS email_messages (
    id TEXT PRIMARY KEY,               -- account_id + ':' + Message-ID
    account_id TEXT NOT NULL,
    thread_key TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    from_email TEXT NOT NULL DEFAULT '', from_name TEXT NOT NULL DEFAULT '',
    to_emails TEXT NOT NULL DEFAULT '[]', cc_emails TEXT NOT NULL DEFAULT '[]',
    sent_at TEXT NOT NULL,
    snippet TEXT NOT NULL DEFAULT '',  -- first ~1500 chars of the text, local only
    is_from_me INTEGER NOT NULL DEFAULT 0,
    is_bulk INTEGER NOT NULL DEFAULT 0,
    message_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS email_threads (
    id TEXT PRIMARY KEY,               -- account_id + ':' + thread key
    account_id TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    counterpart_name TEXT NOT NULL DEFAULT '', counterpart_email TEXT NOT NULL DEFAULT '',
    last_at TEXT NOT NULL,
    last_from_me INTEGER NOT NULL DEFAULT 0,
    last_message_id TEXT NOT NULL DEFAULT '',
    me_direct INTEGER NOT NULL DEFAULT 0,  -- you're in To (not just CC) on the latest message
    is_bulk INTEGER NOT NULL DEFAULT 0,
    needs_reply INTEGER,               -- AI verdict: 1 / 0 / NULL = not triaged
    reason TEXT NOT NULL DEFAULT '',
    urgency TEXT NOT NULL DEFAULT 'normal',
    tasks TEXT NOT NULL DEFAULT '[]',
    triaged_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',    -- open | done | snoozed | dismissed
    snooze_until TEXT,
    notified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_email_messages_thread ON email_messages(account_id, thread_key);
CREATE INDEX IF NOT EXISTS idx_email_threads_open ON email_threads(status, needs_reply);
CREATE INDEX IF NOT EXISTS idx_actions_meeting ON action_items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_topics_meeting ON topics(meeting_id);
CREATE INDEX IF NOT EXISTS idx_topics_name ON topics(name);
CREATE INDEX IF NOT EXISTS idx_shares_token ON shares(token);
CREATE INDEX IF NOT EXISTS idx_mobile_token ON mobile_sessions(mobile_token);
"""

# Placeholder title for a manual recording the user hasn't named (yet).
UNNAMED = "Untitled meeting"

# Idempotent column additions for existing databases.
_MIGRATIONS = {
    "meetings": [
        ("template_id", "TEXT"),
        ("followup_sent", "INTEGER NOT NULL DEFAULT 0"),
        ("coach", "TEXT"),                    # JSON coaching summary
        ("markers", "TEXT NOT NULL DEFAULT '[]'"),  # JSON [seconds,...]
        ("workspace_id", "TEXT"),             # NULL = personal, set = shared to workspace
        ("starred", "INTEGER NOT NULL DEFAULT 0"),
        ("is_demo", "INTEGER NOT NULL DEFAULT 0"),  # onboarding sample meeting, not real AI output
        ("jot_notes", "TEXT NOT NULL DEFAULT ''"),  # what the user jotted during the meeting
        ("ai_paused", "INTEGER NOT NULL DEFAULT 0"),  # free plan's monthly AI notes used up
    ],
    "speaker_events": [("connection", "TEXT NOT NULL DEFAULT 'connected'")],
    "transcripts": [("segments", "TEXT NOT NULL DEFAULT '[]'"),
                    ("speaker_analysis", "TEXT NOT NULL DEFAULT '{}'" )],
    "decisions": [("status", "TEXT NOT NULL DEFAULT 'active'")],
    "calendar_events": [
        ("briefed", "INTEGER NOT NULL DEFAULT 0"),
        ("join_url", "TEXT"),
        ("platform", "TEXT"),
        ("warned_5min", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "action_items": [("completed_at", "TEXT")],
}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    conn.commit()


_schema_lock = threading.Lock()
_schema_ready = False


def get_db() -> sqlite3.Connection:
    global _schema_ready
    conn = getattr(_local, "conn", None)
    if conn is None:
        existed = DB_PATH.exists()
        if not existed:
            touch_secure(DB_PATH)  # 0600 before sqlite ever opens it (C5)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Schema + migrations run once per process, under a lock — two worker
        # threads racing first-run ALTER TABLEs would otherwise collide.
        if not _schema_ready:
            with _schema_lock:
                if not _schema_ready:
                    conn.executescript(SCHEMA)
                    conn.commit()
                    _migrate(conn)
                    _schema_ready = True
        if not existed:
            secure_file(DB_PATH)
        _local.conn = conn
    return conn


def close_db() -> None:
    """Close this thread's connection. Short-lived worker threads (pipeline,
    regenerate) must call this on exit — thread-local connections are otherwise
    reclaimed only by GC, leaking file handles across many recordings."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("attendees", "provider_ids"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                d[key] = []
    return d


def get_setting(key: str, default=None):
    row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return default


def set_setting(key: str, value) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )
    db.commit()
