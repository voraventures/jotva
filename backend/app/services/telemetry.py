"""Anonymous lifecycle telemetry — six events, nothing else.

Contract (see vora-jotva-license/JOTVA_INSTRUMENTATION_SPEC.md and
landing TELEMETRY_DISCLOSURE.md): no meeting content, no transcripts, no
personal data ever. Fixed event enum, random install_id, user-disableable.
Adding an event here requires updating the spec, FAQ, privacy policy, and
Settings copy in the same commit.

STATUS: NOT YET WIRED. Emission points to add during the redesign:
  - emit("app_first_run")            -> backend startup, once (guarded here)
  - emit("first_meeting_completed")  -> after notes generated for meeting #1
  - emit("meeting_milestone_3")      -> after meeting #3 completes
  - emit("free_limit_reached")       -> where the free plan's monthly AI notes run out
      (services/license.py meetings_used() consumers)
  - emit("checkout_opened")          -> where STRIPE_CHECKOUT_URL is opened
Settings UI: expose the 'telemetry_enabled' toggle with the disclosure copy.
"""
import logging
import platform as _platform
import threading

import httpx

from ..config import LICENSE_SERVER_URL
from ..db import get_setting, set_setting

log = logging.getLogger("jotva.telemetry")

EVENTS = frozenset({
    "app_first_run",
    "first_meeting_completed",
    "meeting_milestone_3",
    "free_limit_reached",
    "checkout_opened",
})

# Every event fires at most once per install; guard locally so the server
# never sees dupes and offline retry stays trivial.
_SENT_FLAG = "telemetry_sent_{event}"
_PENDING_FLAG = "telemetry_pending_{event}"
_TIMEOUT_SEC = 3.0


def _app_version() -> str:
    try:
        from ..config import APP_VERSION  # type: ignore[attr-defined]
        return str(APP_VERSION)[:20]
    except Exception:
        return "unknown"


def _install_id() -> str | None:
    try:
        from ..routes.workspace import _install_id as iid
        return iid()
    except Exception as exc:
        log.debug("telemetry: no install_id available: %s", exc)
        return None


def enabled() -> bool:
    """Default on; the Settings toggle writes this key."""
    return get_setting("telemetry_enabled", "1") != "0"


def _post(event: str) -> bool:
    iid = _install_id()
    if not iid:
        return False
    try:
        resp = httpx.post(
            f"{LICENSE_SERVER_URL}/events",
            json={
                "install_id": iid,
                "event": event,
                "app_version": _app_version(),
                "platform": "win" if _platform.system() == "Windows" else "mac",
            },
            timeout=_TIMEOUT_SEC,
        )
        return resp.status_code in (200, 204)
    except Exception as exc:
        log.debug("telemetry: %s not sent (%s)", event, exc)
        return False


def _send(event: str) -> None:
    if _post(event):
        set_setting(_SENT_FLAG.format(event=event), "1")
        set_setting(_PENDING_FLAG.format(event=event), "0")
    else:
        # Queue exactly one retry, flushed on next app launch.
        set_setting(_PENDING_FLAG.format(event=event), "1")


def emit(event: str) -> None:
    """Fire-and-forget. Never raises, never blocks the caller."""
    if event not in EVENTS:
        log.error("telemetry: refusing unknown event %r", event)
        return
    if not enabled():
        return
    if get_setting(_SENT_FLAG.format(event=event), "0") == "1":
        return
    threading.Thread(target=_send, args=(event,), daemon=True).start()


def flush_pending() -> None:
    """Call once at backend startup: retries events that failed offline."""
    if not enabled():
        return
    for event in EVENTS:
        if (
            get_setting(_PENDING_FLAG.format(event=event), "0") == "1"
            and get_setting(_SENT_FLAG.format(event=event), "0") != "1"
        ):
            threading.Thread(target=_send, args=(event,), daemon=True).start()
