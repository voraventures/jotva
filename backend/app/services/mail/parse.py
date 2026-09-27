"""Turn raw email into the small, local record Jotva keeps: who, when, which
conversation, a short text excerpt, and whether it's bulk/automated mail."""
import email
import email.policy
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html import unescape

SNIPPET_CHARS = 1500

_BULK_SENDER = re.compile(
    r"(^|[._+-])(no-?reply|do-?not-?reply|notifications?|mailer-daemon|bounce|news(letter)?|marketing|"
    r"updates?|alerts?|digest|support|billing|receipts?|info|hello|team)([._+-]|@)", re.I)
_QUOTE_START = re.compile(r"^(On .{5,200} wrote:|-{2,}\s*Original Message|From: .+)$", re.M)


def _addresses(values) -> list[tuple[str, str]]:
    """All (name, address) pairs across every copy of a header (To can repeat)."""
    return [(name.strip(), addr.strip().lower()) for name, addr in getaddresses([str(v) for v in values or []]) if addr]


def _text_of(msg) -> str:
    """Plain text of the message (HTML stripped when that's all there is),
    without the quoted history, trimmed to SNIPPET_CHARS."""
    plain, html = None, None
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        ctype = part.get_content_type()
        try:
            content = part.get_content()
        except Exception:
            continue
        if not isinstance(content, str):
            continue
        if ctype == "text/plain" and plain is None:
            plain = content
        elif ctype == "text/html" and html is None:
            html = content
    text = plain
    if text is None and html:
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        text = unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    text = text or ""
    cut = _QUOTE_START.search(text)
    if cut:
        text = text[: cut.start()]
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()[:SNIPPET_CHARS]


def is_bulk(msg, from_email: str) -> bool:
    """Newsletters, notifications and machine mail never 'wait on you'."""
    if msg.get("List-Unsubscribe") or msg.get("List-Id"):
        return True
    if str(msg.get("Precedence", "")).lower() in ("bulk", "list", "junk"):
        return True
    if str(msg.get("Auto-Submitted", "no")).lower() not in ("", "no"):
        return True
    if msg.get_content_type() == "text/calendar" or "method=request" in str(msg.get("Content-Type", "")).lower():
        return True
    return bool(_BULK_SENDER.search(from_email.split("@")[0] + "@"))


def thread_key(msg, message_id: str, provider_thread: str | None = None) -> str:
    """Gmail gives a thread id; otherwise the conversation's first Message-ID
    (from References / In-Reply-To), falling back to the message's own."""
    if provider_thread:
        return provider_thread
    refs = re.findall(r"<[^>]+>", str(msg.get("References", "")) + " " + str(msg.get("In-Reply-To", "")))
    return (refs[0] if refs else message_id).strip("<>").lower()


def parse(raw: bytes, my_addresses: set[str], provider_thread: str | None = None) -> dict | None:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    message_id = str(msg.get("Message-ID", "")).strip()
    if not message_id:
        return None
    from_name, from_email = parseaddr(str(msg.get("From", "")))
    from_email = from_email.lower()
    try:
        sent = parsedate_to_datetime(str(msg.get("Date"))).astimezone(timezone.utc)
    except (TypeError, ValueError):
        sent = datetime.now(timezone.utc)
    to = [a for _, a in _addresses(msg.get_all("To", []))]
    cc = [a for _, a in _addresses(msg.get_all("Cc", []))]
    return {
        "message_id": message_id.strip("<>").lower(),
        "thread_key": thread_key(msg, message_id, provider_thread),
        "subject": str(msg.get("Subject", "")).strip()[:300],
        "from_email": from_email,
        "from_name": (from_name or "").strip()[:120],
        "to": to,
        "cc": cc,
        "sent_at": sent.isoformat(),
        "snippet": _text_of(msg),
        "is_from_me": from_email in my_addresses,
        "is_bulk": is_bulk(msg, from_email),
    }
