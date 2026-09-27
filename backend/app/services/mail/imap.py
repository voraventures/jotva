"""Read-only IMAP: Inbox + Sent for the last SYNC_DAYS days, incrementally.

Only headers and the first part of each body are fetched (never attachments),
and mail is opened with EXAMINE (read-only) so nothing is marked read, moved
or changed on the server."""
import imaplib
import re
from datetime import datetime, timedelta, timezone

SYNC_DAYS = 14
BATCH = 40
PRESETS = {
    "gmail": ("imap.gmail.com", 993),
    "icloud": ("imap.mail.me.com", 993),
}


def connect(host: str, port: int, username: str, password: str) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(host, port, timeout=30)
    conn.login(username, password)
    return conn


def _folders(conn) -> dict[str, str]:
    """{'inbox': name, 'sent': name}; Sent is found by its \\Sent flag."""
    found = {"inbox": "INBOX"}
    typ, rows = conn.list()
    for row in rows or []:
        line = row.decode(errors="replace") if isinstance(row, bytes) else str(row)
        m = re.match(r'\((?P<flags>[^)]*)\)\s+"?[^"]*"?\s+(?P<name>.+)$', line)
        if m and "\\sent" in m.group("flags").lower():
            found["sent"] = m.group("name").strip().strip('"')
    return found


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fetch_new(conn, state: dict, gmail: bool) -> list[tuple[str, bytes, str | None]]:
    """New messages since the stored cursors: [(folder_kind, raw_bytes, gmail_thread_id)].
    Updates `state` in place with each folder's UIDVALIDITY and last UID."""
    out = []
    since = (datetime.now(timezone.utc) - timedelta(days=SYNC_DAYS)).strftime("%d-%b-%Y")
    for kind, folder in _folders(conn).items():
        typ, _ = conn.select(_quote(folder), readonly=True)
        if typ != "OK":
            continue
        validity = (conn.untagged_responses.get("UIDVALIDITY") or [b"0"])[0]
        validity = validity.decode() if isinstance(validity, bytes) else str(validity)
        cursor = state.get(kind) or {}
        if cursor.get("validity") != validity:
            cursor = {"validity": validity, "last_uid": 0}
        if cursor["last_uid"]:
            typ, data = conn.uid("SEARCH", None, f"UID {cursor['last_uid'] + 1}:*")
        else:
            typ, data = conn.uid("SEARCH", None, f"SINCE {since}")
        uids = [int(u) for u in (data[0].split() if data and data[0] else []) if int(u) > cursor["last_uid"]]
        items = "(UID BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.20000>" + (" X-GM-THRID)" if gmail else ")")
        for i in range(0, len(uids), BATCH):
            chunk = ",".join(str(u) for u in uids[i:i + BATCH])
            typ, data = conn.uid("FETCH", chunk, items)
            # imaplib yields (meta, literal) tuples per body section, then a bytes
            # tail (e.g. b' X-GM-THRID 123)') that closes the message.
            parts, meta = [], b""

            def flush():
                thread = re.search(rb"X-GM-THRID (\d+)", meta)
                out.append((kind, b"".join(parts), thread.group(1).decode() if thread else None))

            for entry in data or []:
                if isinstance(entry, tuple):
                    meta += entry[0]
                    parts.append(entry[1])
                elif isinstance(entry, bytes):
                    meta += entry
                    if entry.rstrip().endswith(b")") and parts:
                        flush()
                        parts, meta = [], b""
            if parts:
                flush()
        if uids:
            cursor["last_uid"] = max(uids)
        state[kind] = cursor
    return out
