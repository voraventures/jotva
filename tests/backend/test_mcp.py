"""End-to-end tests for the read-only MCP server (`run.py --mcp`) over stdio, exactly as an
AI assistant launches it. Isolated: temp data dir, no user data."""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

DATA = tempfile.mkdtemp(prefix='jotva-mcp-tests-')
os.environ['JOTVA_DATA_DIR'] = DATA
BACKEND = Path(__file__).resolve().parents[2] / 'backend'
sys.path.insert(0, str(BACKEND))

import anyio
import pytest
from app.config import ensure_dirs, DB_PATH
from app.db import get_db, set_setting
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ensure_dirs()
TOOLS = {"list_meetings", "search_meetings", "get_meeting", "list_action_items", "list_decisions"}


@pytest.fixture(autouse=True)
def seeded():
    db = get_db()
    for table in ("action_items", "decisions", "topics", "transcripts", "notes", "meetings", "settings"):
        db.execute(f"DELETE FROM {table}")
    db.executemany(
        "INSERT INTO meetings(id,title,started_at,ended_at,status,attendees,is_demo) VALUES(?,?,?,?,?,?,?)",
        [("m1", "Pricing review", "2026-09-20T10:00:00", "2026-09-20T10:30:00", "ready", '["Maya Chen"]', 0),
         ("m2", "Onboarding demo", "2026-09-26T09:00:00", "2026-09-26T09:30:00", "ready", "[]", 1)])
    db.execute("INSERT INTO notes VALUES('m1', '## Summary\nEnterprise pricing starts at 40 per seat.', '{}', '2026-09-20')")
    db.execute("INSERT INTO transcripts(meeting_id,text) VALUES('m1', ?)", ("Maya: " + "long talk " * 6000 + "the pricing tiers.",))
    db.execute("INSERT INTO action_items(id,meeting_id,owner,action,due,status) VALUES('a1','m1','Maya Chen','Draft the pricing page','2026-09-30','open')")
    db.execute("INSERT INTO action_items(id,meeting_id,owner,action,due,status) VALUES('a2','m1','TBD','Email finance','','done')")
    db.execute("INSERT INTO decisions(id,meeting_id,text,decided_at) VALUES('d1','m1','Launch enterprise tier in Q4','2026-09-20')")
    db.execute("INSERT INTO topics(id,meeting_id,name) VALUES('t1','m1','Pricing')")
    db.commit()
    set_setting("mcp_enabled", True)
    set_setting("license_status", {"valid": True, "dev": True})  # MCP is a Pro feature


def run(*calls):
    """Launch the server over stdio, run (tool, args) calls, return (tools, results)."""
    async def main():
        params = StdioServerParameters(command=sys.executable, args=["run.py", "--mcp"],
                                       # the data dir the app resolved (another test module may have set it first)
                                       env={"JOTVA_DATA_DIR": str(DB_PATH.parent)}, cwd=str(BACKEND))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                tools = (await s.list_tools()).tools
                return tools, [await s.call_tool(name, args) for name, args in calls]
    return anyio.run(main)


def data(result):
    assert not result.is_error, result.content[0].text
    if result.structured_content is None:  # plain dict results arrive as JSON text
        return json.loads(result.content[0].text)
    return result.structured_content.get("result", result.structured_content)


def test_exposes_only_read_only_tools():
    tools, _ = run()
    assert {t.name for t in tools} == TOOLS
    assert all(t.annotations.read_only_hint for t in tools)


def test_refuses_everything_until_the_user_opts_in():
    set_setting("mcp_enabled", False)
    _, results = run(*[(name, {"query": "x"} if name == "search_meetings" else
                        {"meeting_id": "m1"} if name == "get_meeting" else {}) for name in sorted(TOOLS)])
    for r in results:
        assert r.is_error and "turned off" in r.content[0].text


def test_free_plan_is_told_it_is_a_pro_feature():
    set_setting("license_status", {"valid": False})
    _, (r,) = run(("list_meetings", {}))
    assert r.is_error and "Pro" in r.content[0].text


def test_tools_return_meeting_data():
    _, (meetings, ranged, found, one, actions, done, decisions) = run(
        ("list_meetings", {}),
        ("list_meetings", {"start_date": "2026-09-19", "end_date": "2026-09-20"}),
        ("search_meetings", {"query": "PRICING"}),
        ("get_meeting", {"meeting_id": "m1", "include_transcript": True}),
        ("list_action_items", {}),
        ("list_action_items", {"status": "done"}),
        ("list_decisions", {"query": "enterprise"}),
    )
    assert [m["id"] for m in data(meetings)] == ["m2", "m1"]
    assert data(meetings)[0]["is_sample"] is True
    assert [m["id"] for m in data(ranged)] == ["m1"]
    hit = data(found)
    assert [m["id"] for m in hit] == ["m1"] and any("40 per seat" in e for e in hit[0]["excerpts"])
    m = data(one)
    assert m["title"] == "Pricing review" and m["decisions"] == ["Launch enterprise tier in Q4"]
    assert m["topics"] == ["Pricing"] and len(m["action_items"]) == 2
    assert m["transcript_truncated"] is True and len(m["transcript"]) == 40_000
    assert [a["action"] for a in data(actions)] == ["Draft the pricing page"]
    assert data(actions)[0]["meeting_title"] == "Pricing review"
    assert [a["action"] for a in data(done)] == ["Email finance"]
    assert [d["decision"] for d in data(decisions)] == ["Launch enterprise tier in Q4"]


def test_bad_input_gives_helpful_errors():
    _, (bad_date, missing, bad_status) = run(
        ("list_meetings", {"start_date": "yesterday"}),
        ("get_meeting", {"meeting_id": "nope"}),
        ("list_action_items", {"status": "maybe"}),
    )
    assert bad_date.is_error and "2026-09-26" in bad_date.content[0].text
    assert missing.is_error and "list_meetings" in missing.content[0].text
    assert bad_status.is_error


def test_server_never_writes_to_the_database():
    before = DB_PATH.stat().st_mtime_ns
    run(("search_meetings", {"query": "pricing"}), ("list_action_items", {}))
    assert DB_PATH.stat().st_mtime_ns == before
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM meetings")
    finally:
        conn.close()
