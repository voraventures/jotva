"""Google Calendar via OAuth 2.0 PKCE (public client, no secret on device — C1/C9).

Requires user-supplied client_id in ~/Library/Application Support/Jotva/credentials.json
(see credentials.example.json). Tokens are stored in the OS keychain.
"""
import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.parse

import httpx

from ...config import GOOGLE_CLIENT_ID, LICENSE_SERVER_URL, load_oauth_credentials

log = logging.getLogger("jotva.google")

SCOPES = "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# Token exchange/refresh are brokered server-side so the client_secret never
# lives on the device — the broker holds it. See vora-jotva-license.
OAUTH_BROKER = f"{LICENSE_SERVER_URL}/oauth/google"

# CSRF state tokens with TTL (C9)
_pending: dict[str, dict] = {}
STATE_TTL = 600

try:
    import keyring
except Exception:  # pragma: no cover
    keyring = None

_KC = "Jotva"


def _save_tokens(tokens: dict) -> None:
    if keyring:
        keyring.set_password(_KC, "google_oauth_tokens", json.dumps(tokens))


def _load_tokens() -> dict | None:
    if keyring:
        raw = keyring.get_password(_KC, "google_oauth_tokens")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    return None


def clear_tokens() -> None:
    if keyring:
        try:
            keyring.delete_password(_KC, "google_oauth_tokens")
        except Exception:
            pass


def _cleanup_states() -> None:
    now = time.time()
    for state in [s for s, v in _pending.items() if now - v["created"] > STATE_TTL]:
        del _pending[state]


def client_id() -> str | None:
    creds = load_oauth_credentials()
    return creds.get("google", {}).get("client_id") or GOOGLE_CLIENT_ID


def is_connected() -> bool:
    return _load_tokens() is not None


def build_auth_url(redirect_uri: str) -> str:
    cid = client_id()
    if not cid:
        raise RuntimeError(
            "Google client_id not configured — add credentials.json (see credentials.example.json)"
        )
    _cleanup_states()
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(24)
    _pending[state] = {
        "verifier": verifier,
        "redirect_uri": redirect_uri,
        "created": time.time(),
    }
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(state: str, code: str) -> None:
    _cleanup_states()
    pending = _pending.pop(state, None)
    if pending is None:
        raise RuntimeError("Invalid or expired OAuth state")
    resp = httpx.post(
        f"{OAUTH_BROKER}/exchange",
        json={
            "code": code,
            "redirect_uri": pending["redirect_uri"],
            "code_verifier": pending["verifier"],
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600) - 60
    _save_tokens(tokens)


def get_access_token() -> str | None:
    tokens = _load_tokens()
    if not tokens:
        return None
    if time.time() < tokens.get("expires_at", 0):
        return tokens["access_token"]
    refresh = tokens.get("refresh_token")
    if not refresh:
        return None
    try:
        resp = httpx.post(
            f"{OAUTH_BROKER}/refresh",
            json={"refresh_token": refresh},
            timeout=15,
        )
        resp.raise_for_status()
        fresh = resp.json()
        tokens["access_token"] = fresh["access_token"]
        tokens["expires_at"] = time.time() + fresh.get("expires_in", 3600) - 60
        _save_tokens(tokens)
        return tokens["access_token"]
    except httpx.HTTPError as exc:
        log.warning("Google token refresh failed: %s", exc)
        return None


def fetch_events(time_min_iso: str, time_max_iso: str) -> list[dict]:
    token = get_access_token()
    if not token:
        return []
    try:
        resp = httpx.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "timeMin": time_min_iso,
                "timeMax": time_max_iso,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 50,
                "showDeleted": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Google events fetch failed: %s", exc)
        return []
    events = []
    for item in resp.json().get("items", []):
        start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
        end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
        if not start:
            continue
        events.append(
            {
                "provider": "google",
                "provider_id": item.get("id", ""),
                "title": item.get("summary", "Untitled event"),
                "start": start,
                "end": end,
                "attendees": [
                    a.get("displayName") or a.get("email", "")
                    for a in item.get("attendees", [])
                ],
                "cancelled": item.get("status") == "cancelled",
                "native_link": item.get("hangoutLink"),
                "location": item.get("location"),
                "description": item.get("description"),
            }
        )
    return events
