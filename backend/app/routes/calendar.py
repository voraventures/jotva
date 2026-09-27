"""Calendar connection + sync routes. The Google OAuth callback is the only
unauthenticated HTML route (the browser redirect can't carry our token); it is
protected by the PKCE state token with TTL instead (C9)."""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..db import get_db, get_setting, set_setting
from ..services import presence
from ..services.calendars import apple_cal, google_cal, ms_cal, sync

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
oauth_router = APIRouter(tags=["oauth"])  # mounted without auth dependency


class AppleToggle(BaseModel):
    enabled: bool


class ModeBody(BaseModel):
    mode: str


@router.get("/status")
def status():
    return {
        **sync.connection_status(),
        "recording_mode": get_setting("recording_mode", "confirm_30s"),
    }


@router.post("/sync")
def sync_now():
    count = sync.sync_now()
    return {"synced": count}


@router.get("/upcoming")
def upcoming():
    return sync.upcoming_events()


@router.get("/brief/{event_id}")
def brief(event_id: str):
    """Pre-meeting intelligence, on demand."""
    import json as _json

    from fastapi import HTTPException

    from ..db import get_db
    from ..services.intelligence import meeting_brief

    db = get_db()
    ev = db.execute(
        "SELECT * FROM calendar_events WHERE id=?", (event_id,)
    ).fetchone()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    attendees = _json.loads(ev["attendees"] or "[]")
    return {
        "event_id": ev["id"],
        "title": ev["title"],
        "start": ev["start"],
        **meeting_brief(attendees, ev["title"]),
    }


@router.post("/events/{event_id}/join")
def join_event(event_id: str):
    """Returns the meeting link for the renderer to open, and starts watching
    live audio so recording is offered once people actually start talking."""
    ev = get_db().execute(
        "SELECT join_url, cancelled FROM calendar_events WHERE id=?", (event_id,)
    ).fetchone()
    if not ev or ev["cancelled"]:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"join_url": ev["join_url"], "watching": presence.start_watch(event_id)}


@router.post("/mode")
def set_mode(body: ModeBody):
    if body.mode not in ("all", "confirm_30s", "manual", "off"):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Invalid mode")
    if body.mode == "all":
        from ..services import license

        license.require_pro("auto_record")
    set_setting("recording_mode", body.mode)
    return {"ok": True, "mode": body.mode}


@router.post("/google/connect")
def google_connect(request: Request):
    port = request.url.port
    redirect_uri = f"http://127.0.0.1:{port}/oauth/google/callback"
    url = google_cal.build_auth_url(redirect_uri)
    return {"auth_url": url}


@router.post("/google/disconnect")
def google_disconnect():
    google_cal.clear_tokens()
    return {"ok": True}


@router.post("/microsoft/connect")
def ms_connect():
    return ms_cal.start_device_flow()


@router.post("/microsoft/disconnect")
def ms_disconnect():
    ms_cal.clear_tokens()
    return {"ok": True}


@router.post("/apple/toggle")
def apple_toggle(body: AppleToggle):
    set_setting("apple_calendar_enabled", body.enabled)
    if body.enabled and apple_cal.probe_access() == "access_denied":
        return {"ok": False, "error": "access_denied"}
    return {"ok": True, "enabled": body.enabled}


_CALLBACK_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Jotva</title>
<style>body{font-family:-apple-system,sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;background:#fbfaf6;color:#1e281d}
.card{text-align:center;padding:40px;border-radius:16px;background:#fff;
box-shadow:0 4px 24px rgba(30,40,29,.08)}h1{color:#3f8b45;font-size:22px}</style>
</head><body><div class="card"><h1>{title}</h1><p>{message}</p>
<p>You can close this tab and return to Jotva.</p></div></body></html>"""


@oauth_router.get("/oauth/google/callback")
def google_callback(
    state: str = Query(default=""),
    code: str = Query(default=""),
    error: str = Query(default=""),
):
    if error or not code:
        html = _CALLBACK_HTML.replace("{title}", "Connection cancelled").replace(
            "{message}", "Google Calendar was not connected."
        )
        return HTMLResponse(html, status_code=400)
    try:
        purpose, tokens = google_cal.exchange_code(state, code)
    except Exception:
        html = _CALLBACK_HTML.replace("{title}", "Connection failed").replace(
            "{message}", "The sign-in link expired. Try again from Settings."
        )
        return HTMLResponse(html, status_code=400)
    from ..events import hub

    if purpose == "gmail":
        from ..services.mail import gmail

        try:
            account = gmail.finish_connect(tokens)
        except Exception:
            html = _CALLBACK_HTML.replace("{title}", "Gmail not connected").replace(
                "{message}", "Google didn't grant access to Gmail. Try again from Jotva → Settings."
            )
            return HTMLResponse(html, status_code=400)
        hub.emit("email_updated", {"connected": account["address"]})
        html = _CALLBACK_HTML.replace("{title}", "Gmail connected").replace(
            "{message}", "Jotva will now show the emails waiting on you. You can close this tab."
        )
        return HTMLResponse(html)

    hub.emit("google_connected", {})
    sync.sync_now()
    html = _CALLBACK_HTML.replace("{title}", "Google Calendar connected").replace(
        "{message}", "Jotva will now watch this calendar for meetings."
    )
    return HTMLResponse(html)
