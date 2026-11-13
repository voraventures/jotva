"""Export notes as PDF (fpdf2), Markdown, or plain text. Files land in EXPORTS_DIR."""
import re
import sys
from datetime import datetime
from pathlib import Path

from ..config import EXPORTS_DIR, secure_file, touch_secure, write_secure_text

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_HEADER = re.compile(r"^(#{1,3})\s+(.*)$")
# Violet brand, matching the desktop accent. Latin-1 PDF text stays Helvetica.
_BRAND = (107, 88, 230)
_INK = (22, 21, 42)


def _safe_name(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", title).strip() or "meeting"
    return cleaned[:60].replace(" ", "_")


def _logo_path() -> Path | None:
    """Locate the Jotva logo: PyInstaller bundle first (sys._MEIPASS/assets),
    then the dev project tree. Returns None if unavailable so PDFs render
    text-only rather than crashing."""
    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / "icon.png")
    candidates.append(
        Path(__file__).resolve().parents[3] / "electron" / "assets" / "icon.png"
    )
    for c in candidates:
        try:
            if c.exists():
                return c
        except OSError:
            continue
    return None


def _logo_header(pdf, subtitle: str | None = None) -> None:
    """Draw the Jotva logo (16x16mm) + wordmark top-left, optional subtitle below.
    Falls back to wordmark-only if the logo asset can't be found/read."""
    logo = _logo_path()
    x = pdf.l_margin
    top = pdf.get_y()
    text_x = x
    if logo is not None:
        try:
            pdf.image(str(logo), x=x, y=top, w=16, h=16)
            text_x = x + 19
        except Exception:
            text_x = x
    pdf.set_xy(text_x, top + 3)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*_BRAND)
    pdf.cell(0, 9, "Jotva", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), top + 16) + 2)
    if subtitle:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*_INK)
        safe = subtitle.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 7, safe, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def export_markdown(title: str, markdown: str) -> Path:
    path = EXPORTS_DIR / f"{_safe_name(title)}.md"
    write_secure_text(path, f"# {title}\n\n{markdown}\n")
    return path


def export_text(title: str, markdown: str) -> Path:
    text = _MD_BOLD.sub(r"\1", markdown)
    lines = []
    for line in text.splitlines():
        m = _MD_HEADER.match(line)
        if m:
            heading = m.group(2).upper()
            lines.append(heading)
            lines.append("=" * len(heading))
        else:
            lines.append(line)
    path = EXPORTS_DIR / f"{_safe_name(title)}.txt"
    write_secure_text(path, f"{title.upper()}\n{'=' * len(title)}\n\n" + "\n".join(lines))
    return path


def export_pdf(title: str, markdown: str) -> Path:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    def w(text, size=11, style="", color=_INK, spacing=6):
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*color)
        safe = text.encode("latin-1", "replace").decode("latin-1")
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, spacing, safe, new_x="LMARGIN", new_y="NEXT")

    _logo_header(pdf)
    w(title, size=20, style="B", color=_BRAND, spacing=9)
    pdf.ln(3)

    in_table = False
    for line in markdown.splitlines():
        stripped = line.strip()
        header = _MD_HEADER.match(stripped)
        if header:
            pdf.ln(3)
            w(header.group(2), size=14, style="B", color=_BRAND, spacing=8)
            in_table = False
        elif stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= {"-", ":", " "} for c in cells):
                continue
            style = "B" if not in_table else ""
            w("   ".join(_MD_BOLD.sub(r"\1", c) for c in cells), size=10, style=style, spacing=5)
            in_table = True
        elif stripped.startswith(("-", "*")):
            w("  •  " + _MD_BOLD.sub(r"\1", stripped.lstrip("-* ")), spacing=5.5)
            in_table = False
        elif stripped:
            w(_MD_BOLD.sub(r"\1", stripped), spacing=5.5)
            in_table = False
        else:
            pdf.ln(2)

    path = EXPORTS_DIR / f"{_safe_name(title)}.pdf"
    touch_secure(path)  # 0600 before fpdf writes content
    pdf.output(str(path))
    secure_file(path)
    return path


EXPORTERS = {"pdf": export_pdf, "markdown": export_markdown, "text": export_text}


# ---------- Export Pack: cross-meeting premium exports ----------

def export_actions_csv() -> Path:
    """All action items: owner, action, due, meeting, date, status."""
    import csv

    from ..db import get_db

    path = EXPORTS_DIR / "jotva-actions.csv"
    touch_secure(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Owner", "Action", "Due", "Meeting", "Meeting date", "Status"])
        for r in get_db().execute(
            """SELECT a.owner, a.action, a.due, m.title, m.started_at, a.status
               FROM action_items a JOIN meetings m ON m.id=a.meeting_id
               ORDER BY m.started_at DESC"""
        ):
            writer.writerow(
                [r["owner"], r["action"], r["due"], r["title"], r["started_at"][:10], r["status"]]
            )
    secure_file(path)
    return path


def export_timeline_pdf() -> Path:
    """Chronological decision log across all meetings."""
    from fpdf import FPDF

    from ..db import get_db

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    def w(text, size=11, style="", color=_INK, spacing=6):
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*color)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            0, spacing, text.encode("latin-1", "replace").decode("latin-1"),
            new_x="LMARGIN", new_y="NEXT",
        )

    _logo_header(pdf)
    w("Jotva — Decision Timeline", size=20, style="B", color=_BRAND, spacing=9)
    pdf.ln(4)
    current_date = None
    for r in get_db().execute(
        """SELECT d.text, d.status, d.decided_at, m.title
           FROM decisions d JOIN meetings m ON m.id=d.meeting_id
           ORDER BY d.decided_at"""
    ):
        date = r["decided_at"][:10]
        if date != current_date:
            pdf.ln(2)
            w(date, size=12, style="B", color=_BRAND, spacing=7)
            current_date = date
        suffix = "  [superseded]" if r["status"] == "superseded" else ""
        w(f"  -  {r['text']}{suffix}", size=10.5, spacing=5.5)
        w(f"      from: {r['title']}", size=9, color=(118, 123, 114), spacing=4.5)

    path = EXPORTS_DIR / "jotva-decision-timeline.pdf"
    touch_secure(path)
    pdf.output(str(path))
    secure_file(path)
    return path


def export_my_actions_pdf(meeting_id: str, user_name: str) -> Path:
    """One meeting's action items owned by user_name, as a branded PDF checklist."""
    from fpdf import FPDF

    from ..db import get_db

    db = get_db()
    meeting = db.execute("SELECT title FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    title = meeting["title"] if meeting else "Meeting"
    rows = db.execute(
        "SELECT action, due, status FROM action_items "
        "WHERE meeting_id=? AND LOWER(owner)=LOWER(?) ORDER BY status, due",
        (meeting_id, user_name),
    ).fetchall()

    def _l1(text: str) -> str:
        return (text or "").encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    _logo_header(pdf, title)

    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*_BRAND)
    pdf.multi_cell(0, 8, _l1(f"Your action items - {user_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    if not rows:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(118, 123, 114)
        pdf.multi_cell(
            0, 6, _l1("No action items assigned to you in this meeting."),
            new_x="LMARGIN", new_y="NEXT",
        )
    else:
        box = 4.5
        for r in rows:
            done = r["status"] == "done"
            y = pdf.get_y()
            pdf.set_draw_color(*_BRAND)
            pdf.set_fill_color(*_BRAND)
            pdf.set_line_width(0.4)
            pdf.rect(pdf.l_margin, y + 0.6, box, box, style="DF" if done else "D")
            pdf.set_xy(pdf.l_margin + box + 3, y)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(*_INK)
            due = f"  (due {r['due']})" if r["due"] else ""
            badge = "DONE" if done else "OPEN"
            pdf.multi_cell(
                0, 6, _l1(f"{r['action']}{due}   [{badge}]"),
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.ln(1.5)

    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(118, 123, 114)
    pdf.multi_cell(
        0, 5, _l1(f"Generated by Jotva - {datetime.now().strftime('%Y-%m-%d')}"),
        new_x="LMARGIN", new_y="NEXT",
    )

    path = EXPORTS_DIR / f"{_safe_name(title)}-my-actions.pdf"
    touch_secure(path)
    pdf.output(str(path))
    secure_file(path)
    return path


def slack_digest(title: str, sections: dict) -> str:
    """Slack-flavored markdown summary, ready to paste."""
    parts = [f"*{title}*"]
    if sections.get("Executive Summary"):
        parts.append(sections["Executive Summary"].replace("**", "*"))
    if sections.get("Decisions Made"):
        parts.append("*Decisions*\n" + sections["Decisions Made"].replace("**", "*"))
    if sections.get("Action Items"):
        rows = [
            line for line in sections["Action Items"].splitlines()
            if line.strip().startswith("|") and "Owner" not in line and "---" not in line
        ]
        actions = []
        for row in rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if len(cells) >= 2:
                due = f" _(due {cells[2]})_" if len(cells) > 2 and cells[2] else ""
                actions.append(f"• *{cells[0]}* — {cells[1]}{due}")
        if actions:
            parts.append("*Action items*\n" + "\n".join(actions))
    return "\n\n".join(parts)
