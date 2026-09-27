"""Jotva backend: FastAPI app with token auth, CORS allowlist, host-header
allowlist, rate limiting, and generic external error messages (C2/C3/C7/C8)."""
import asyncio
import logging
import sys

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import SESSION_TOKEN, check_ws_auth, require_token
from .config import ALLOWED_HOSTS, ALLOWED_ORIGINS, DEV_MODE, ensure_dirs
from .events import hub
from .ratelimit import check_rate_limit
from .routes import billing, calendar, email, intelligence, meetings, misc, mobile, recording, share, system, workspace, speakers

log = logging.getLogger("jotva")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)


def create_app() -> FastAPI:
    ensure_dirs()
    app = FastAPI(title="Jotva", docs_url=None, redoc_url=None, openapi_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,  # explicit list; no wildcards, no file:// (C3)
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Jotva-Token"],
    )

    @app.middleware("http")
    async def host_allowlist(request: Request, call_next):
        # DNS-rebinding defense (C3): only loopback hosts may address us.
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def bound_speaker_messages(request: Request, call_next):
        if request.url.path.startswith('/speaker-bridge/'):
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16384:
                    return JSONResponse({'detail': 'Message too large'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        return await call_next(request)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        try:
            check_rate_limit(request)
        except Exception as exc:  # HTTPException from limiter
            status = getattr(exc, "status_code", 429)
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=status)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def generic_error(request: Request, exc: Exception):
        # C8: full traceback server-side only; generic message externally.
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    authed = [Depends(require_token)]
    app.include_router(recording.router, dependencies=authed)
    app.include_router(speakers.router, dependencies=authed)
    app.include_router(speakers.bridge_router)
    app.include_router(meetings.router, dependencies=authed)
    app.include_router(intelligence.router, dependencies=authed)
    app.include_router(calendar.router, dependencies=authed)
    app.include_router(misc.router, dependencies=authed)
    app.include_router(billing.router, dependencies=authed)
    app.include_router(email.router, dependencies=authed)
    app.include_router(share.router, dependencies=authed)
    app.include_router(system.router, dependencies=authed)
    app.include_router(workspace.router, dependencies=authed)
    # Mobile API uses its own token auth (X-Mobile-Token), but the desktop-token
    # guard still wraps /api/mobile/auth so only the local app can mint tokens.
    app.include_router(mobile.router, dependencies=authed)
    # OAuth browser callback: protected by single-use PKCE state w/ TTL, not token.
    app.include_router(calendar.oauth_router)
    # DEV ONLY: tier-switch testing endpoint, registered only in development.
    if DEV_MODE:
        from .routes import dev as dev_routes

        app.include_router(dev_routes.router, dependencies=authed)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        if not check_ws_auth(ws):
            await ws.close(code=4401)
            return
        await hub.connect(ws)
        try:
            while True:
                await ws.receive_text()  # keepalive pings from client
        except WebSocketDisconnect:
            hub.disconnect(ws)

    @app.on_event("startup")
    async def on_startup():
        hub.set_loop(asyncio.get_running_loop())
        from .services.calendars.sync import start_poller

        start_poller()
        from .services.mail.sync import start_poller as start_email_poller

        start_email_poller()

        # Salvage meetings interrupted by a crash/force-quit in a prior session.
        from .services.pipeline import recover_interrupted

        try:
            recover_interrupted()
        except Exception:
            log.exception("Interrupted-meeting recovery failed")

        # Speaker separation is on by default; fetch its pinned local models
        # (~46 MB, checksum-verified) in the background the first time.
        from .db import get_setting
        from .services import speaker_models

        try:
            if get_setting("speaker_identification", True) and not speaker_models.ready() \
                    and speaker_models.status()["runtime_available"]:
                speaker_models.install()
        except Exception:
            log.exception("Speaker model download could not start")

    return app
