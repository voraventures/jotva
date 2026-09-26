"""Local, read-only MCP server: lets AI assistants (Claude Desktop, Cursor, ...) read the
user's Jotva meetings. The assistant launches it over stdio (`jotva-backend --mcp`).

Opt-in: every call re-checks the `mcp_enabled` setting, so switching it off in Jotva takes
effect immediately. The database is opened read-only, and audio is never exposed. Anything
an assistant reads is sent to that assistant's provider — the Settings UI says so.
"""
import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .config import DB_PATH

TRANSCRIPT_LIMIT = 40_000
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

server = MCPServer(
    name="jotva",
    title="Jotva",
    instructions=(
        "Jotva is the user's private, on-device meeting notes app. Use these tools to answer "
        "questions about their meetings: search_meetings to find where something was discussed, "
        "get_meeting for a meeting's full notes, list_action_items for open tasks, "
        "list_decisions for what was decided. Meetings flagged is_sample are onboarding demos, "
        "not real conversations. Cite meeting titles and dates in answers."
    ),
)


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise ToolError("No Jotva data on this Mac yet. Record a meeting in Jotva first.")
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT value FROM settings WHERE key = 'mcp_enabled'").fetchone()
    if not row or json.loads(row["value"]) is not True:
        conn.close()
        raise ToolError(
            "Access to Jotva is turned off. The user can allow it in Jotva → Settings → "
            "Integrations → AI assistants."
        )
    return conn


def _clamp(limit: int, top: int = 100) -> int:
    return max(1, min(int(limit), top))


def _day(value: str, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{field} must be a date like 2026-09-26")


def _meeting(r: sqlite3.Row) -> dict:
    keys = r.keys()
    return {
        "id": r["id"],
        "title": r["title"],
        "started_at": r["started_at"],
        "ended_at": r["ended_at"],
        "status": r["status"],
        "attendees": json.loads(r["attendees"] or "[]"),
        "is_sample": bool(r["is_demo"]) if "is_demo" in keys else False,
    }


def _excerpt(text: str | None, needle: str, width: int = 90) -> str | None:
    if not text:
        return None
    at = text.lower().find(needle.lower())
    if at < 0:
        return None
    start, end = max(0, at - width), min(len(text), at + len(needle) + width)
    return ("…" if start else "") + " ".join(text[start:end].split()) + ("…" if end < len(text) else "")


@server.tool(annotations=READ_ONLY)
def list_meetings(start_date: str = "", end_date: str = "", limit: int = 20) -> list[dict]:
    """List the user's meetings, newest first. Optional start_date / end_date (YYYY-MM-DD,
    inclusive) narrow the range."""
    start, end = _day(start_date, "start_date"), _day(end_date, "end_date")
    sql, args = "SELECT * FROM meetings WHERE 1=1", []
    if start:
        sql += " AND started_at >= ?"; args.append(start.isoformat())
    if end:
        sql += " AND started_at < ?"; args.append((end + timedelta(days=1)).isoformat())
    sql += " ORDER BY started_at DESC LIMIT ?"; args.append(_clamp(limit))
    with closing(_connect()) as conn:
        return [_meeting(r) for r in conn.execute(sql, args)]


@server.tool(annotations=READ_ONLY)
def search_meetings(query: str, limit: int = 10) -> list[dict]:
    """Find meetings that mention `query` in their title, AI notes, transcript or action
    items. Returns each match with short excerpts showing where it came up."""
    query = query.strip()
    if not query:
        raise ToolError("query must not be empty")
    like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT DISTINCT m.*, n.content AS notes, t.text AS transcript FROM meetings m
               LEFT JOIN notes n ON n.meeting_id = m.id
               LEFT JOIN transcripts t ON t.meeting_id = m.id
               LEFT JOIN action_items a ON a.meeting_id = m.id
               WHERE m.title LIKE ?1 ESCAPE '\\' OR n.content LIKE ?1 ESCAPE '\\'
                  OR t.text LIKE ?1 ESCAPE '\\' OR a.action LIKE ?1 ESCAPE '\\'
                  OR a.owner LIKE ?1 ESCAPE '\\'
               ORDER BY m.started_at DESC LIMIT ?2""",
            (like, _clamp(limit, 50)),
        ).fetchall()
        results = []
        for r in rows:
            hit = _meeting(r)
            hit["excerpts"] = [e for e in (_excerpt(r["notes"], query), _excerpt(r["transcript"], query)) if e]
            results.append(hit)
        return results


@server.tool(annotations=READ_ONLY)
def get_meeting(meeting_id: str, include_transcript: bool = False) -> dict:
    """One meeting's full AI notes (summary, action items, decisions, topics). Set
    include_transcript to also get the verbatim transcript (long; truncated if huge)."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not row:
            raise ToolError(f"No meeting with id {meeting_id!r}. Use list_meetings or search_meetings to find ids.")
        meeting = _meeting(row)
        note = conn.execute("SELECT content FROM notes WHERE meeting_id = ?", (meeting_id,)).fetchone()
        meeting["notes_markdown"] = note["content"] if note else None
        if "jot_notes" in row.keys():
            meeting["user_jots"] = row["jot_notes"] or None
        meeting["action_items"] = [
            {"action": a["action"], "owner": a["owner"], "due": a["due"] or None, "status": a["status"]}
            for a in conn.execute("SELECT * FROM action_items WHERE meeting_id = ?", (meeting_id,))
        ]
        meeting["decisions"] = [d["text"] for d in conn.execute(
            "SELECT text FROM decisions WHERE meeting_id = ?", (meeting_id,))]
        meeting["topics"] = [t["name"] for t in conn.execute(
            "SELECT name FROM topics WHERE meeting_id = ?", (meeting_id,))]
        if include_transcript:
            t = conn.execute("SELECT text FROM transcripts WHERE meeting_id = ?", (meeting_id,)).fetchone()
            text = t["text"] if t else None
            meeting["transcript"] = text[:TRANSCRIPT_LIMIT] if text else None
            meeting["transcript_truncated"] = bool(text and len(text) > TRANSCRIPT_LIMIT)
        return meeting


@server.tool(annotations=READ_ONLY)
def list_action_items(status: str = "open", owner: str = "", limit: int = 50) -> list[dict]:
    """Action items across all meetings, newest meeting first. status is "open", "done" or
    "all"; owner filters by (partial) name."""
    if status not in ("open", "done", "all"):
        raise ToolError('status must be "open", "done" or "all"')
    sql = ("SELECT a.*, m.title, m.started_at FROM action_items a JOIN meetings m ON m.id = a.meeting_id "
           "WHERE 1=1")
    args: list = []
    if status != "all":
        sql += " AND a.status = ?"; args.append(status)
    if owner.strip():
        sql += " AND a.owner LIKE ?"; args.append(f"%{owner.strip()}%")
    sql += " ORDER BY m.started_at DESC LIMIT ?"; args.append(_clamp(limit))
    with closing(_connect()) as conn:
        return [{"action": r["action"], "owner": r["owner"], "due": r["due"] or None, "status": r["status"],
                 "meeting_id": r["meeting_id"], "meeting_title": r["title"], "meeting_date": r["started_at"]}
                for r in conn.execute(sql, args)]


@server.tool(annotations=READ_ONLY)
def list_decisions(query: str = "", limit: int = 30) -> list[dict]:
    """Decisions recorded across meetings, newest first. query optionally filters by text."""
    sql = ("SELECT d.text, d.meeting_id, m.title, m.started_at FROM decisions d "
           "JOIN meetings m ON m.id = d.meeting_id")
    args: list = []
    if query.strip():
        sql += " WHERE d.text LIKE ?"; args.append(f"%{query.strip()}%")
    sql += " ORDER BY m.started_at DESC LIMIT ?"; args.append(_clamp(limit))
    with closing(_connect()) as conn:
        return [{"decision": r["text"], "meeting_id": r["meeting_id"], "meeting_title": r["title"],
                 "meeting_date": r["started_at"]} for r in conn.execute(sql, args)]


def main() -> None:
    server.run("stdio")
