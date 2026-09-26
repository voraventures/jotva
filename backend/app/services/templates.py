"""Meeting templates: shape how Claude structures the notes.

A template's `body` describes its specific sections. Every template is then
composed with the SHARED TAIL (Decisions Made + Action Items + Next Steps) so
cross-meeting intelligence (actions, decisions, topics, conflicts) keeps
working regardless of template.
"""
from ..db import get_db, new_id, now_iso

GROUNDING_RULE = """GROUNDING — the single most important rule, overriding every
other instruction below: every fact, name, number, date, owner, and quote you
write must come from the transcript. Never infer, assume, or invent content
that is not present, even to fill a section that expects one. If a section
has nothing to report, write "Not discussed." instead of manufacturing
content. An action item or decision gets a named owner ONLY if the transcript
shows that person saying or being assigned it — otherwise the owner is "TBD",
regardless of who the note is being generated for."""

SHARED_RULES = """Rules for every section:
- Mark each major theme with a **Bold Topic Phrase** at the start of its line
  or bullet — these power cross-meeting topic intelligence.
- Be specific with names, numbers, and dates. Keep the total under 800 words.
- Use level-2 markdown headers (##) exactly matching the section names given.
- In the Executive Summary section only, wrap the single most pivotal phrase
  (the crux of what changed or was decided) in *single asterisks* for emphasis."""

SHARED_TAIL = """## Decisions Made
A bullet list of genuine decisions or agreements (a choice made, an option
ruled out, a direction set). Do not restate action items here. If none, write
"- No decisions recorded."

## Action Items
A markdown table with exactly these columns: | Owner | Action | Due |
Use "TBD" for unknown owners. Due is YYYY-MM-DD, or "" when no date is known.

## Next Steps
A short bullet list of what happens next."""

BUILTINS = [
    {
        "id": "builtin-default",
        "name": "Default",
        "description": "Executive notes: summary, discussions, decisions, actions, compliance.",
        "body": """## Executive Summary
2-4 sentences capturing what the meeting accomplished and why it matters.

## Key Discussions
For each major topic: a **Bold Topic Phrase** followed by a concise summary.

{SHARED_TAIL}

## Compliance Flags
Bullet list of anything legally or contractually sensitive. If none, "- None identified." """,
    },
    {
        "id": "builtin-sales",
        "name": "Sales Call (MEDDIC)",
        "description": "Metrics, Economic Buyer, Decision Criteria/Process, Pain, Champion.",
        "body": """## Executive Summary
2-3 sentences: deal stage, momentum, and the single most important takeaway.

## Metrics
Quantified value the prospect cares about. **Bold** each metric theme.

## Economic Buyer
Who controls budget; were they present; access plan.

## Decision Criteria
What the prospect will judge solutions on.

## Decision Process
Steps, timeline, and who is involved in the buying decision.

## Identify Pain
The business pain driving this evaluation. **Bold** each pain theme.

## Champion
Who is selling internally for us; strength of the champion.

{SHARED_TAIL}""",
    },
    {
        "id": "builtin-oneonone",
        "name": "1-on-1",
        "description": "Personal development, blockers, feedback, growth.",
        "body": """## Executive Summary
2-3 sentences on the state of this person and the relationship.

## Personal Development
Growth themes, aspirations, skills in progress. **Bold** each theme.

## Blockers
What is slowing them down — with severity.

## Feedback Exchanged
Feedback given and received, both directions.

{SHARED_TAIL}""",
    },
    {
        "id": "builtin-discovery",
        "name": "Product Discovery",
        "description": "User problem, insights, hypotheses, evidence.",
        "body": """## Executive Summary
2-3 sentences: what we learned and how it changes our thinking.

## User Problem
The problem as the user articulated it. **Bold** each problem theme.

## Insights
Surprising or load-bearing observations, with verbatim quotes where powerful.

## Hypotheses
What we now believe and how we could test it.

{SHARED_TAIL}""",
    },
    {
        "id": "builtin-board",
        "name": "Board Meeting",
        "description": "Agenda items, formal decisions, owners, follow-ups.",
        "body": """## Executive Summary
3-4 sentences a board member would accept as the official short record.

## Agenda Items
For each item: a **Bold Item Name**, the discussion essence, and the outcome.

{SHARED_TAIL}

## Follow-ups
Commitments made to the board with timing.""",
    },
    {
        "id": "builtin-interview",
        "name": "Interview",
        "description": "Candidate evaluation: criteria, strengths, concerns, recommendation.",
        "body": """## Executive Summary
2 sentences: candidate, role, overall read.

## Candidate & Role
Name, role interviewed for, interviewer(s), stage.

## Evaluation Criteria
The dimensions assessed in this conversation. **Bold** each criterion.

## Strengths
Evidence-backed strengths with examples from the conversation.

## Concerns
Specific concerns and the evidence behind them.

## Recommendation
Hire signal: Strong yes / Yes / No / Strong no — with one-line rationale.

{SHARED_TAIL}""",
    },
    {
        "id": "builtin-sprint",
        "name": "Sprint Planning",
        "description": "Sprint goal, stories, estimates, risks, blockers.",
        "body": """## Executive Summary
2 sentences: the sprint goal and confidence in it.

## Sprint Goal
The single goal in one crisp sentence.

## Stories Discussed
For each story: **Bold Story Name**, scope notes, owner if assigned.

## Estimates
Sizing discussed, disagreements, final numbers.

## Risks
What could sink the sprint. **Bold** each risk theme.

## Blockers
Current blockers and who unblocks them.

{SHARED_TAIL}""",
    },
    {
        "id": "builtin-cs",
        "name": "Customer Success",
        "description": "Health, risks, expansion, commitments.",
        "body": """## Executive Summary
2-3 sentences: account health and trajectory.

## Health Indicators
Usage, sentiment, stakeholder engagement. **Bold** each indicator theme.

## Risks
Churn signals with severity and evidence.

## Expansion Opportunities
Upsell/cross-sell openings discussed.

{SHARED_TAIL}""",
    },
]

_BUILTIN_IDS = {t["id"] for t in BUILTINS}


def compose_system_prompt(template: dict) -> str:
    body = template["body"].replace("{SHARED_TAIL}", SHARED_TAIL)
    return (
        "You are Jotva, an elite meeting-intelligence analyst. You turn raw "
        "meeting transcripts into precise, outcome-focused notes for busy "
        f"executives.\n\n{GROUNDING_RULE}\n\nProduce ONLY markdown with exactly "
        f"these level-2 sections, in this order:\n\n{body}\n\n{SHARED_RULES}"
    )


def list_templates() -> list[dict]:
    db = get_db()
    custom = [
        {**dict(r), "builtin": False}
        for r in db.execute("SELECT * FROM templates ORDER BY created_at")
    ]
    return [{**t, "builtin": True} for t in BUILTINS] + custom


def get_template(template_id: str | None) -> dict:
    if template_id:
        for t in BUILTINS:
            if t["id"] == template_id:
                return t
        row = get_db().execute(
            "SELECT * FROM templates WHERE id=?", (template_id,)
        ).fetchone()
        if row:
            return dict(row)
    return BUILTINS[0]


def create_template(name: str, description: str, body: str) -> dict:
    db = get_db()
    tid = new_id()
    db.execute(
        "INSERT INTO templates(id,name,description,body,created_at) VALUES(?,?,?,?,?)",
        (tid, name, description, body, now_iso()),
    )
    db.commit()
    return {"id": tid, "name": name, "description": description, "body": body, "builtin": False}


def update_template(template_id: str, name: str, description: str, body: str) -> bool:
    if template_id in _BUILTIN_IDS:
        return False
    db = get_db()
    cur = db.execute(
        "UPDATE templates SET name=?, description=?, body=? WHERE id=?",
        (name, description, body, template_id),
    )
    db.commit()
    return cur.rowcount > 0


def delete_template(template_id: str) -> bool:
    if template_id in _BUILTIN_IDS:
        return False
    db = get_db()
    cur = db.execute("DELETE FROM templates WHERE id=?", (template_id,))
    db.commit()
    return cur.rowcount > 0


def section_names(template: dict) -> list[str]:
    """Section names for coach topic-coverage tracking."""
    import re

    body = template["body"].replace("{SHARED_TAIL}", SHARED_TAIL)
    return re.findall(r"^## (.+)$", body, flags=re.M)
