"""Freemium plan + Pro license validated against the remote server.

Free, forever: unlimited recording and on-device transcription, plus AI notes for
FREE_AI_NOTES_PER_MONTH meetings a month through the bundled AI. Pro unlocks
unlimited notes and the power features in PRO_FEATURES. A free user never loses
access to anything they already have — past notes stay readable and exportable."""
import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx

from fastapi import HTTPException

from ..config import (
    LICENSE_PUBLIC_KEY_PEM,
    LICENSE_SERVER_URL,
    STRIPE_CHECKOUT_URL,
)
from ..db import get_db, get_setting, set_setting
from .keychain import get_secret, set_secret

log = logging.getLogger("jotva.license")

# AI notes a free install gets each calendar month via the bundled AI (Vora pays).
# Users who bring their own AI key pay their provider, so they aren't counted.
FREE_AI_NOTES_PER_MONTH = 10

# Pro-only features. Keys are shared with the UI (license.features) and 402 errors.
PRO_FEATURES = (
    "unlimited_notes",   # no monthly cap on bundled-AI notes
    "higher_quality",    # the Pro AI tier (Sonnet-class)
    "live_notes",        # AI notes that build up during the meeting
    "ask_all",           # Ask across every meeting
    "auto_record",       # calendar auto-start ("all" recording mode)
    "mcp",               # AI-assistant access over MCP
    "followup",          # follow-up email drafts
    "templates",         # custom note templates
    "integrations",      # Slack / Notion / workspace sharing
)

# Offline grace: a previously-validated license stays valid 72h without re-check.
OFFLINE_GRACE_SEC = 72 * 3600

# DEV ONLY: local development license — activates Pro indefinitely without
# ever contacting the license server. Never publish this key.
DEV_LICENSE_KEY = os.environ.get("JOTVA_DEV_KEY", "")


try:
    import keyring as _keyring
except Exception:  # pragma: no cover
    _keyring = None

_KC_SERVICE = "Jotva"
_KC_COUNTER = "lifetime_meeting_counter"


def _keychain_counter() -> int:
    if _keyring is None:
        return 0
    try:
        raw = _keyring.get_password(_KC_SERVICE, _KC_COUNTER)
        return int(raw) if raw and raw.isdigit() else 0
    except Exception:
        return 0


def record_meeting_created() -> None:
    """Monotonic lifetime counter in the OS keychain — deleting the local DB
    cannot reset the free-tier allowance."""
    if _keyring is None:
        return
    try:
        _keyring.set_password(_KC_SERVICE, _KC_COUNTER, str(_keychain_counter() + 1))
    except Exception as exc:
        log.warning("Could not bump keychain meeting counter: %s", exc)


def meetings_used() -> int:
    db_count = get_db().execute("SELECT COUNT(*) c FROM meetings").fetchone()["c"]
    return max(db_count, _keychain_counter())


def _month() -> str:
    return datetime.now().strftime("%Y-%m")


def _kc_month_key(month: str) -> str:
    return f"ai_notes_{month}"


def _keychain_month_count(month: str) -> int:
    if _keyring is None:
        return 0
    try:
        raw = _keyring.get_password(_KC_SERVICE, _kc_month_key(month))
        return int(raw) if raw and raw.isdigit() else 0
    except Exception:
        return 0


def ai_notes_used(month: str | None = None) -> int:
    """Meetings that got bundled-AI notes this month. Mirrored in the keychain so
    deleting meetings or the database can't reset the allowance."""
    month = month or _month()
    db_count = get_db().execute(
        "SELECT COUNT(*) c FROM ai_note_usage WHERE month=?", (month,)
    ).fetchone()["c"]
    return max(db_count, _keychain_month_count(month))


def uses_bundled_ai() -> bool:
    """True when notes go through Vora's bundled AI rather than the user's own key."""
    return get_setting("ai_provider", "anthropic") == "anthropic" and not get_secret("anthropic_api_key")


def is_pro() -> bool:
    cached = get_setting("license_status", {})
    if cached.get("dev"):  # DEV ONLY
        return True
    return bool(cached.get("valid")) and (time.time() - cached.get("checked_at", 0) < OFFLINE_GRACE_SEC)


def has_feature(feature: str) -> bool:
    return feature not in PRO_FEATURES or is_pro()


def require_pro(feature: str) -> None:
    """Raise 402 for a Pro-only feature on the free plan. The UI keys its upgrade
    prompt off `code`/`feature`; `message` is the human-readable fallback."""
    if not has_feature(feature):
        raise HTTPException(
            status_code=402,
            detail={"code": "pro_required", "feature": feature,
                    "message": "This is a Jotva Pro feature. Upgrade to unlock it."},
        )


def can_write_ai_notes(meeting_id: str | None = None) -> bool:
    """Pro, a user's own key, a meeting already counted (regenerating), or free
    allowance left this month."""
    if is_pro() or not uses_bundled_ai():
        return True
    if meeting_id and get_db().execute(
        "SELECT 1 FROM ai_note_usage WHERE meeting_id=?", (meeting_id,)
    ).fetchone():
        return True
    return ai_notes_used() < FREE_AI_NOTES_PER_MONTH


def record_ai_notes(meeting_id: str) -> None:
    """Count a meeting against the free monthly allowance (once per meeting)."""
    if is_pro() or not uses_bundled_ai():
        return
    month = _month()
    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO ai_note_usage(meeting_id, month, created_at) VALUES(?,?,?)",
        (meeting_id, month, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    if cur.rowcount and _keyring is not None:
        try:
            _keyring.set_password(_KC_SERVICE, _kc_month_key(month),
                                  str(max(_keychain_month_count(month), ai_notes_used(month) - 1) + 1))
        except Exception as exc:
            log.warning("Could not bump keychain AI-notes counter: %s", exc)


def _sync_install_id_key() -> None:
    """The Stripe webhook keys the issued license to the install_id, so the
    install_id IS the license key — users never enter one manually. Keep the
    keychain license_key in sync with the install_id, but never clobber a dev key."""
    from ..routes.workspace import _install_id

    current = get_secret("license_key")
    if DEV_LICENSE_KEY and current == DEV_LICENSE_KEY:
        return
    iid = _install_id()
    if current != iid:
        try:
            set_secret("license_key", iid)
        except Exception as exc:  # a keychain refusal must never break the plan screen
            log.warning("Could not store license key in the keychain: %s", exc)


def status() -> dict:
    _sync_install_id_key()  # on app start: ensure license_key == install_id
    pro = is_pro()
    used = ai_notes_used()
    bundled = uses_bundled_ai()
    return {
        "tier": "pro" if pro else "free",
        "plan_name": "Pro" if pro else "Free",
        "meetings_used": meetings_used(),
        "can_record": True,  # recording + transcription are free forever
        # Free plan's monthly AI-notes allowance (None = unlimited: Pro or own key).
        "ai_notes_limit": None if pro or not bundled else FREE_AI_NOTES_PER_MONTH,
        "ai_notes_used": used,
        "ai_notes_remaining": None if pro or not bundled else max(0, FREE_AI_NOTES_PER_MONTH - used),
        "ai_notes_resets_on": _next_month_start(),
        "features": {f: pro for f in PRO_FEATURES},
        "checkout_url": STRIPE_CHECKOUT_URL,
        "license_key_set": bool(get_secret("license_key")),
    }


def _next_month_start() -> str:
    now = datetime.now()
    return (now.replace(year=now.year + 1, month=1, day=1) if now.month == 12
            else now.replace(month=now.month + 1, day=1)).date().isoformat()


def activate(license_key: str) -> dict:
    key = license_key.strip()
    set_secret("license_key", key)
    if DEV_LICENSE_KEY and key == DEV_LICENSE_KEY:  # DEV ONLY: bypass the remote server entirely
        set_setting("license_status", {"valid": True, "dev": True, "checked_at": time.time()})
        return status()
    return refresh()


def _reset_keychain_counter() -> None:  # DEV ONLY
    """DEV ONLY: zero the monotonic free-tier counter so usage resets."""
    if _keyring is None:
        return
    try:
        _keyring.set_password(_KC_SERVICE, _KC_COUNTER, "0")
    except Exception as exc:
        log.warning("Could not reset keychain meeting counter: %s", exc)


def set_tier(tier: str) -> dict:  # DEV ONLY
    """DEV ONLY: flip local license state between free and pro without touching
    the license server. 'pro' mirrors the AGUA-DEV-LOCAL-2026 bypass; 'free'
    clears the cached license and resets the usage counter."""
    if tier == "pro":
        set_setting("license_status", {"valid": True, "dev": True, "checked_at": time.time()})
    else:
        set_setting("license_status", {"valid": False, "checked_at": time.time()})
        _reset_keychain_counter()
        month = _month()
        get_db().execute("DELETE FROM ai_note_usage WHERE month=?", (month,))
        get_db().commit()
        if _keyring is not None:
            try:
                _keyring.set_password(_KC_SERVICE, _kc_month_key(month), "0")
            except Exception:
                pass
    return status()


def _verify_signed_license(data: dict, install_id: str) -> bool:
    """A license is valid only if its RSA-SHA256 signature verifies against the
    bundled public key, it names THIS install, and it has not expired. An HTTP
    200 from whatever JOTVA_LICENSE_SERVER points at proves nothing."""
    payload = data.get("payload")
    signature_b64 = data.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature_b64, str):
        return False
    if payload.get("install_id") != install_id or payload.get("tier") != "pro":
        return False
    try:
        expires = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return False
    except (KeyError, ValueError, TypeError):
        return False
    try:
        import base64

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        public_key = serialization.load_pem_public_key(LICENSE_PUBLIC_KEY_PEM.encode())
        # Must byte-match the server's canonicalization:
        # json.dumps(payload, sort_keys=True, separators=(",", ":"))
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        public_key.verify(
            base64.b64decode(signature_b64),
            canonical,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as exc:
        log.warning("License signature verification failed: %s", exc)
        return False


def refresh() -> dict:
    """Validate the stored license key against the license server."""
    _sync_install_id_key()  # after checkout: ensure we validate the install_id
    from ..routes.workspace import _install_id

    key = get_secret("license_key") or _install_id()  # the key IS the install id
    if not key:
        set_setting("license_status", {"valid": False, "checked_at": time.time()})
        return status()
    if key == DEV_LICENSE_KEY:  # DEV ONLY: dev license never re-validates remotely
        set_setting("license_status", {"valid": True, "dev": True, "checked_at": time.time()})
        return status()
    try:
        resp = httpx.get(
            f"{LICENSE_SERVER_URL}/license/{key}",
            timeout=10,
        )
        data = resp.json() if resp.status_code == 200 else {}
        valid = (
            resp.status_code == 200
            and not data.get("error")
            and _verify_signed_license(data, key)
        )
        set_setting("license_status", {"valid": valid, "checked_at": time.time()})
        # Cache the fresh portal token the server mints on each lookup; the
        # billing-portal call presents it to prove ownership of this install.
        if valid and data.get("portal_token"):
            try:
                set_secret("portal_token", data["portal_token"])
            except Exception as exc:  # keychain unavailable — non-fatal
                log.warning("Could not store portal token: %s", exc)
    except httpx.HTTPError as exc:
        log.warning("License server unreachable: %s", exc)
        # keep previous cached status (offline grace handled in status())
    return status()
