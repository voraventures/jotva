"""Cross-meeting intelligence: parse notes into structured data, heads-up logic,
related-meeting scoring, and aggregate Actions/Decisions/Topics/People views."""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ..db import get_db, new_id, now_iso, row_to_dict
from .notes import split_sections

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")


_ISO_DAY_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def normalize_due(due: str, action: str) -> tuple[str, str]:
    """Due cells should be a bare YYYY-MM-DD, but models add notes like
    "2026-09-30 (by 3 p.m.)". Keep the date, move the note into the action, and
    if the note names a weekday the date doesn't fall on, snap the date to the
    nearest such weekday (models are unreliable at weekday arithmetic)."""
    from datetime import date, timedelta

    m = _ISO_DAY_RE.search(due or "")
    if not m:
        return (due or "").strip(), action
    iso = m.group(1)
    note = (due[: m.start()] + due[m.end():]).strip(" ()-–,;")
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        return iso, action
    named = [i for i, w in enumerate(_WEEKDAYS) if w in note.lower()]
    if len(named) == 1 and day.weekday() != named[0]:
        shift = (named[0] - day.weekday()) % 7
        day += timedelta(days=shift if shift <= 3 else shift - 7)
    if note and note.lower() not in action.lower():
        action = f"{action} ({note})"
    return day.isoformat(), action


def index_notes(meeting_id: str, markdown: str) -> dict:
    """Parse notes markdown and (re)build action_items/decisions/topics rows."""
    db = get_db()
    sections = split_sections(markdown)

    db.execute("DELETE FROM action_items WHERE meeting_id=?", (meeting_id,))
    db.execute("DELETE FROM decisions WHERE meeting_id=?", (meeting_id,))
    db.execute("DELETE FROM topics WHERE meeting_id=?", (meeting_id,))

    # --- Action items: markdown table | Owner | Action | Due |
    actions = []
    for line in sections.get("Action Items", "").splitlines():
        m = TABLE_ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 2:
            continue
        if cells[0].lower() == "owner" or set(cells[0]) <= {"-", ":", " "}:
            continue  # header / separator rows
        owner = cells[0] or "TBD"
        action = cells[1] if len(cells) > 1 else ""
        due, action = normalize_due(cells[2] if len(cells) > 2 else "", action)
        if not action:
            continue
        aid = new_id()
        db.execute(
            "INSERT INTO action_items(id,meeting_id,owner,action,due) VALUES(?,?,?,?,?)",
            (aid, meeting_id, owner, action, due),
        )
        actions.append({"id": aid, "owner": owner, "action": action, "due": due})

    # --- Decisions: bullets under Decisions Made
    decisions = []
    for line in sections.get("Decisions Made", "").splitlines():
        line = line.strip()
        if line.startswith(("-", "*")):
            text = line.lstrip("-* ").strip()
            if text and not text.lower().startswith("no decisions"):
                did = new_id()
                db.execute(
                    "INSERT INTO decisions(id,meeting_id,text,decided_at) VALUES(?,?,?,?)",
                    (did, meeting_id, text, now_iso()),
                )
                decisions.append({"id": did, "text": text})

    # --- Topics: bold phrases from all narrative sections (template-agnostic)
    topics = []
    seen = set()
    topic_source = "\n".join(
        body
        for name, body in sections.items()
        if name not in ("Action Items", "Decisions Made", "Flagged Moments")
    )
    for phrase in BOLD_RE.findall(topic_source):
        name = phrase.strip().rstrip(":").strip()
        key = name.lower()
        if name and key not in seen and len(name) < 80:
            seen.add(key)
            db.execute(
                "INSERT INTO topics(id,meeting_id,name) VALUES(?,?,?)",
                (new_id(), meeting_id, name),
            )
            topics.append(name)

    db.commit()
    return {"actions": actions, "decisions": decisions, "topics": topics, "sections": sections}


def heads_up(meeting_id: str) -> list[str]:
    """Warnings: TBD/empty owners on actions, or actions without any decisions."""
    db = get_db()
    flags = []
    rows = db.execute(
        "SELECT owner FROM action_items WHERE meeting_id=?", (meeting_id,)
    ).fetchall()
    unowned = sum(1 for r in rows if r["owner"].strip().upper() in ("", "TBD", "?"))
    if unowned:
        plural = "s" if unowned != 1 else ""
        flags.append(
            f"{unowned} action item{plural} ha{'ve' if unowned != 1 else 's'} no owner — assign before they slip."
        )
    n_decisions = db.execute(
        "SELECT COUNT(*) c FROM decisions WHERE meeting_id=?", (meeting_id,)
    ).fetchone()["c"]
    if rows and n_decisions == 0:
        flags.append(
            "Action items were created but no decisions were recorded — confirm the team aligned on direction."
        )
    return flags


def related_meetings(meeting_id: str, limit: int = 4) -> list[dict]:
    """Score other meetings by shared topic phrases (case-insensitive)."""
    db = get_db()
    mine = {
        r["name"].lower()
        for r in db.execute("SELECT name FROM topics WHERE meeting_id=?", (meeting_id,))
    }
    if not mine:
        return []
    scores: dict[str, set] = defaultdict(set)
    for r in db.execute(
        "SELECT meeting_id, name FROM topics WHERE meeting_id != ?", (meeting_id,)
    ):
        if r["name"].lower() in mine:
            scores[r["meeting_id"]].add(r["name"])
    ranked = sorted(scores.items(), key=lambda kv: len(kv[1]), reverse=True)[:limit]
    out = []
    for mid, shared in ranked:
        m = db.execute(
            "SELECT id, title, started_at FROM meetings WHERE id=?", (mid,)
        ).fetchone()
        if m:
            out.append(
                {
                    "meeting_id": m["id"],
                    "title": m["title"],
                    "started_at": m["started_at"],
                    "shared_topics": sorted(shared),
                    "score": len(shared),
                }
            )
    return out


def aggregate_actions() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT a.*, m.title AS meeting_title, m.started_at AS meeting_date
           FROM action_items a JOIN meetings m ON m.id = a.meeting_id
           ORDER BY m.started_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def aggregate_decisions() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT d.*, m.title AS meeting_title, m.started_at AS meeting_date
           FROM decisions d JOIN meetings m ON m.id = d.meeting_id
           ORDER BY m.started_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def aggregate_topics() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT t.name, t.meeting_id, m.title AS meeting_title, m.started_at AS meeting_date
           FROM topics t JOIN meetings m ON m.id = t.meeting_id"""
    ).fetchall()
    grouped: dict[str, dict] = {}
    for r in rows:
        key = r["name"].lower()
        g = grouped.setdefault(
            key, {"name": r["name"], "mentions": 0, "meetings": []}
        )
        g["mentions"] += 1
        g["meetings"].append(
            {"id": r["meeting_id"], "title": r["meeting_title"], "date": r["meeting_date"]}
        )
    # Trend: split each topic's meetings into recent (last 30d) vs older.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    for g in grouped.values():
        recent = sum(1 for mt in g["meetings"] if (mt["date"] or "")[:10] >= cutoff)
        older = len(g["meetings"]) - recent
        if len(g["meetings"]) < 2 or recent == older:
            g["trend"] = "recurring"
        else:
            g["trend"] = "rising" if recent > older else "fading"
    return sorted(grouped.values(), key=lambda g: g["mentions"], reverse=True)


def _name_subset(short: str, long: str) -> bool:
    """True if `short` is a distinct whole-word substring of `long`."""
    if short == long:
        return False
    return re.search(rf"\b{re.escape(short.lower())}\b", long.lower()) is not None


def _merge_people(people: dict[str, dict]) -> list[dict]:
    """Fuzzy-merge owners where one name is a whole-word substring of a longer
    one ('Devin' -> 'Devin Park'); the longer name is canonical."""
    canon: list[dict] = []
    for p in sorted(people.values(), key=lambda p: len(p["name"]), reverse=True):
        target = next((c for c in canon if _name_subset(p["name"], c["name"])), None)
        if target:
            target["action_count"] += p["action_count"]
            target["open_actions"] += p["open_actions"]
            target["meeting_count"] += p["meeting_count"]
            for a in p["recent_actions"]:
                if len(target["recent_actions"]) < 3:
                    target["recent_actions"].append(a)
        else:
            canon.append(p)
    return canon


def aggregate_people() -> list[dict]:
    db = get_db()
    people: dict[str, dict] = {}

    def bucket(name: str) -> dict:
        canon = name.strip().title()
        return people.setdefault(
            canon.lower(), {"name": canon, "action_count": 0, "open_actions": 0,
                  "recent_actions": [], "meeting_count": 0}
        )

    for r in db.execute(
        """SELECT a.owner, a.action, a.due, a.status, m.title AS meeting_title, a.meeting_id
           FROM action_items a JOIN meetings m ON m.id=a.meeting_id
           ORDER BY m.started_at DESC"""
    ):
        owner = r["owner"].strip()
        if not owner or owner.upper() == "TBD":
            continue
        p = bucket(owner)
        p["action_count"] += 1
        if r["status"] == "open":
            p["open_actions"] += 1
        if len(p["recent_actions"]) < 3:
            p["recent_actions"].append(
                {"action": r["action"], "due": r["due"], "status": r["status"],
                 "meeting_id": r["meeting_id"], "meeting_title": r["meeting_title"]}
            )

    for r in db.execute("SELECT attendees FROM meetings"):
        try:
            names = json.loads(r["attendees"])
        except json.JSONDecodeError:
            names = []
        for n in names:
            if isinstance(n, str) and n.strip():
                bucket(n)["meeting_count"] += 1

    return sorted(_merge_people(people), key=lambda p: p["action_count"], reverse=True)


def _norm_series_title(title: str) -> str:
    """Normalize a recurring-meeting title: strip dates, numbers, week refs."""
    t = title.lower()
    t = re.sub(r"\b\d{1,2}[/.-]\d{1,2}([/.-]\d{2,4})?\b", "", t)  # dates
    t = re.sub(r"\b(week|wk|sprint|w)\s*#?\d+\b", r"\1", t)
    t = re.sub(r"#?\d+", "", t)
    return re.sub(r"\s+", " ", t).strip(" -—:")


def detect_series() -> list[dict]:
    """Recurring meetings: same normalized title, 2+ occurrences."""
    db = get_db()
    meetings = db.execute(
        "SELECT id, title, started_at FROM meetings ORDER BY started_at"
    ).fetchall()
    groups: dict[str, list] = defaultdict(list)
    for m in meetings:
        key = _norm_series_title(m["title"])
        if key:
            groups[key].append(m)

    series = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        ids = [m["id"] for m in items]
        ph = ",".join("?" * len(ids))
        open_actions = db.execute(
            f"SELECT COUNT(*) c FROM action_items WHERE meeting_id IN ({ph}) AND status='open'",
            ids,
        ).fetchone()["c"]
        done_actions = db.execute(
            f"SELECT COUNT(*) c FROM action_items WHERE meeting_id IN ({ph}) AND status='done'",
            ids,
        ).fetchone()["c"]
        topic_rows = db.execute(
            f"SELECT name, COUNT(DISTINCT meeting_id) n FROM topics "
            f"WHERE meeting_id IN ({ph}) GROUP BY LOWER(name) HAVING n >= 2 "
            f"ORDER BY n DESC LIMIT 8",
            ids,
        ).fetchall()
        # cadence: median gap between consecutive occurrences; tolerate rows
        # with unparseable dates rather than 500ing the whole series view
        dates = []
        for m in items:
            try:
                dates.append(datetime.fromisoformat(m["started_at"]))
            except (TypeError, ValueError):
                pass
        gaps = sorted(
            (dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)
        )
        cadence_days = gaps[len(gaps) // 2] if gaps else 0
        completion = (
            round(done_actions / (open_actions + done_actions) * 100)
            if open_actions + done_actions
            else None
        )
        series.append(
            {
                "key": key,
                "name": items[-1]["title"],
                "count": len(items),
                "cadence_days": cadence_days,
                "open_actions": open_actions,
                "done_actions": done_actions,
                "completion_pct": completion,
                "recurring_topics": [
                    {"name": r["name"], "meetings": r["n"]} for r in topic_rows
                ],
                "meetings": [
                    {"id": m["id"], "title": m["title"], "date": m["started_at"]}
                    for m in reversed(items)
                ],
            }
        )
    return sorted(series, key=lambda s: s["count"], reverse=True)


def aggregate_conflicts() -> list[dict]:
    """Open contradictions between decisions as flat pairs. Each row already
    pairs the two conflicting decisions with both meeting sources."""
    db = get_db()
    rows = db.execute(
        """SELECT c.id, c.new_decision, c.old_decision, c.explanation, c.created_at,
                  c.meeting_id AS new_meeting_id, m.title AS new_meeting_title,
                  m.started_at AS new_date,
                  c.old_meeting_id, c.old_meeting_title, c.old_date
           FROM conflicts c JOIN meetings m ON m.id = c.meeting_id
           WHERE c.status='open'
           ORDER BY c.created_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def action_pulse() -> dict:
    """Daily action hygiene: stale actions, actions owned by people you meet
    today, momentum stats."""
    db = get_db()
    now = datetime.now(timezone.utc)
    stale_cutoff = (now - timedelta(days=14)).isoformat()
    stale = [
        dict(r)
        for r in db.execute(
            """SELECT a.*, m.title AS meeting_title, m.started_at AS meeting_date
               FROM action_items a JOIN meetings m ON m.id=a.meeting_id
               WHERE a.status='open' AND m.started_at < ?
               ORDER BY m.started_at LIMIT 20""",
            (stale_cutoff,),
        )
    ]
    # attendees of today's calendar events
    today = now.date().isoformat()
    todays_people: set[str] = set()
    for r in db.execute(
        "SELECT attendees FROM calendar_events WHERE start LIKE ? AND cancelled=0",
        (f"{today}%",),
    ):
        try:
            todays_people.update(a.lower() for a in json.loads(r["attendees"]))
        except json.JSONDecodeError:
            pass
    due_with_today = []
    if todays_people:
        due_with_today = [
            dict(r)
            for r in db.execute(
                """SELECT a.*, m.title AS meeting_title FROM action_items a
                   JOIN meetings m ON m.id=a.meeting_id WHERE a.status='open'"""
            )
            if r["owner"].lower() in todays_people
        ]
    return {
        "stale_actions": stale,
        "stale_count": len(stale),
        "meeting_today_actions": due_with_today[:10],
        **my_work_summary(),
    }


def digest_summary(period: str = "week") -> dict:
    """Auto-generated rollup for the Digest screen: real meetings, recurring
    topics, and aggregated actions/decisions in the period — no per-item
    fabricated data. The frontend templates the hero sentence from these
    numbers itself (i18n-friendly) rather than a new LLM call."""
    db = get_db()
    now = datetime.now(timezone.utc)
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=7)

    rows = db.execute(
        "SELECT id, title, started_at, ended_at FROM meetings "
        "WHERE started_at >= ? AND started_at < ? ORDER BY started_at",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    ids = [r["id"] for r in rows]

    meetings = []
    total_minutes = 0
    for r in rows:
        dur_min = 0
        if r["ended_at"]:
            started = datetime.fromisoformat(r["started_at"])
            ended = datetime.fromisoformat(r["ended_at"])
            dur_min = round((ended - started).total_seconds() / 60)
            total_minutes += dur_min
        day = datetime.fromisoformat(r["started_at"]).strftime("%a").upper()
        meetings.append(
            {"id": r["id"], "title": r["title"], "duration_min": dur_min, "day": day}
        )

    topics, open_actions, decisions = [], [], []
    if ids:
        ph = ",".join("?" * len(ids))
        topics = [
            dict(row)
            for row in db.execute(
                f"""SELECT name, COUNT(DISTINCT meeting_id) n FROM topics
                    WHERE meeting_id IN ({ph}) GROUP BY LOWER(name)
                    ORDER BY n DESC, name LIMIT 10""",
                ids,
            ).fetchall()
        ]
        open_actions = [
            dict(row)
            for row in db.execute(
                f"""SELECT a.*, m.title AS meeting_title FROM action_items a
                    JOIN meetings m ON m.id = a.meeting_id
                    WHERE a.meeting_id IN ({ph}) AND a.status='open'
                    ORDER BY m.started_at""",
                ids,
            ).fetchall()
        ]
        decisions = [
            dict(row)
            for row in db.execute(
                f"""SELECT * FROM decisions WHERE meeting_id IN ({ph})
                    AND status='active' ORDER BY decided_at""",
                ids,
            ).fetchall()
        ]

    return {
        "period": period,
        "range_start": start.isoformat(),
        "range_end": (end - timedelta(seconds=1)).isoformat(),
        "meeting_count": len(meetings),
        "total_minutes": total_minutes,
        "meetings": meetings,
        "recurring_topics": topics,
        "open_actions": open_actions,
        "decisions": decisions,
    }


def meeting_brief(attendees: list[str], title: str) -> dict:
    """Pre-meeting intelligence: history with these attendees / this series."""
    db = get_db()
    wanted = {a.strip().lower() for a in attendees if a and a.strip()}
    series_key = _norm_series_title(title)

    related_ids = []
    for m in db.execute(
        "SELECT id, title, attendees, started_at FROM meetings ORDER BY started_at DESC LIMIT 100"
    ):
        try:
            names = {a.lower() for a in json.loads(m["attendees"])}
        except json.JSONDecodeError:
            names = set()
        if (wanted and names & wanted) or (
            series_key and _norm_series_title(m["title"]) == series_key
        ):
            related_ids.append(m["id"])
    related_ids = related_ids[:8]
    if not related_ids:
        return {"meetings": [], "open_actions": [], "decisions": [], "talking_points": []}

    ph = ",".join("?" * len(related_ids))
    meetings = [
        dict(r)
        for r in db.execute(
            f"SELECT id, title, started_at FROM meetings WHERE id IN ({ph}) "
            f"ORDER BY started_at DESC",
            related_ids,
        )
    ]
    open_actions = [
        dict(r)
        for r in db.execute(
            f"""SELECT a.*, m.title AS meeting_title FROM action_items a
                JOIN meetings m ON m.id=a.meeting_id
                WHERE a.meeting_id IN ({ph}) AND a.status='open' LIMIT 12""",
            related_ids,
        )
    ]
    decisions = [
        dict(r)
        for r in db.execute(
            f"""SELECT d.*, m.title AS meeting_title FROM decisions d
                JOIN meetings m ON m.id=d.meeting_id
                WHERE d.meeting_id IN ({ph}) AND d.status='active'
                ORDER BY d.decided_at DESC LIMIT 10""",
            related_ids,
        )
    ]
    talking_points = [
        f"{a['owner']}: {a['action']}" + (f" (due {a['due']})" if a["due"] else "")
        for a in open_actions[:6]
    ]
    return {
        "meetings": meetings,
        "open_actions": open_actions,
        "decisions": decisions,
        "talking_points": talking_points,
    }


def my_work_summary() -> dict:
    db = get_db()
    open_actions = db.execute(
        "SELECT COUNT(*) c FROM action_items WHERE status='open'"
    ).fetchone()["c"]
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    decisions_week = db.execute(
        "SELECT COUNT(*) c FROM decisions WHERE decided_at >= ?", (week_ago,)
    ).fetchone()["c"]
    meetings_processed = db.execute(
        "SELECT COUNT(*) c FROM meetings WHERE status='ready'"
    ).fetchone()["c"]
    return {
        "open_actions": open_actions,
        "decisions_this_week": decisions_week,
        "meetings_processed": meetings_processed,
    }


def meeting_intelligence(meeting_id: str) -> dict:
    """Everything the notes panel needs for the AI metadata bar + cards."""
    db = get_db()
    actions = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM action_items WHERE meeting_id=?", (meeting_id,)
        )
    ]
    decisions = [
        dict(r)
        for r in db.execute("SELECT * FROM decisions WHERE meeting_id=?", (meeting_id,))
    ]
    meeting = db.execute(
        "SELECT attendees FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()
    participants = []
    if meeting:
        try:
            participants = json.loads(meeting["attendees"])
        except json.JSONDecodeError:
            participants = []
    topics = [
        r["name"]
        for r in db.execute(
            "SELECT DISTINCT name FROM topics WHERE meeting_id=? ORDER BY name",
            (meeting_id,),
        )
    ]
    return {
        "actions": actions,
        "decisions": decisions,
        "participants": participants,
        "topics": topics,
        "heads_up": heads_up(meeting_id),
        "related": related_meetings(meeting_id),
    }
