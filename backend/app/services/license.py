"""Freemium plan + Pro license validated against the remote server.

Pro is a license SIGNED by the license server (RSA, bundled public key). The app stores the signed
license itself and re-verifies the signature, the install id and the expiry every time it asks
"is this install Pro?" (is_pro). There is no unsigned or developer shortcut anywhere: editing the
local database, the settings or the environment cannot make an install Pro. A developer gets Pro
the way a customer does, with a license the server signs for their install.

Free, forever: unlimited recording and on-device transcription, plus AI notes for
FREE_AI_NOTES_PER_MONTH meetings a month through the bundled AI. Pro unlocks
unlimited notes and the power features in PRO_FEATURES. A free user never loses
access to anything they already have — past notes stay readable and exportable."""
import json
import logging
import threading
import time
from functools import lru_cache
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
    "email",             # "Waiting on you": emails that still need a reply
    "agent",             # one task list across meetings, live notes and email
    "own_key",           # bring your own AI key (Anthropic / OpenAI / Google)
    "ask_all",           # Ask across every meeting
    "auto_record",       # calendar auto-start ("all" recording mode)
    "mcp",               # AI-assistant access over MCP
    "followup",          # follow-up email drafts
    "templates",         # custom note templates
    "integrations",      # Slack / Notion / workspace sharing
)

# A signed license carries its own expiry (the server issues ~35 days at each renewal), so a Pro
# install keeps working offline until then and never longer. The app re-fetches it regularly.


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
    if not is_pro():  # own keys are a Pro feature: Free always uses the included AI
        return True
    return get_setting("ai_provider", "anthropic") == "anthropic" and not get_secret("anthropic_api_key")


def is_pro() -> bool:
    """True only for a license the server signed for THIS install and that has not expired. The
    stored license is re-verified on every call; nothing else in the settings is believed."""
    return signed_license_valid(get_setting("license_signed"), _this_install_id())


def _this_install_id() -> str:
    from ..routes.workspace import _install_id

    return _install_id()


def signed_license_valid(signed, install_id: str) -> bool:
    """Shared by the app and the MCP server (which reads the same database)."""
    return isinstance(signed, dict) and bool(install_id) and _verify_signed_license(signed, install_id)


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
    keychain license_key in sync with the install_id."""
    from ..routes.workspace import _install_id

    current = get_secret("license_key")
    iid = _install_id()
    if current != iid:
        try:
            set_secret("license_key", iid)
        except Exception as exc:  # a keychain refusal must never break the plan screen
            log.warning("Could not store license key in the keychain: %s", exc)


_migration_started = False


def _migrate_legacy_flag() -> None:
    """Earlier versions kept Pro as a bare yes/no flag. If one is there but no signed license is
    stored yet, fetch the signed license once in the background (paying customers keep Pro), and
    drop the old flag, including any "dev" marker, so nothing unsigned lingers in the database."""
    global _migration_started
    if _migration_started:
        return
    _migration_started = True
    legacy = get_setting("license_status")
    if not isinstance(legacy, dict):
        return
    if legacy.get("dev") or legacy.get("valid"):
        set_setting("license_status", {"valid": False, "checked_at": 0})
        if not isinstance(get_setting("license_signed"), dict):
            threading.Thread(target=refresh, daemon=True, name="license-migrate").start()


def status() -> dict:
    _sync_install_id_key()  # on app start: ensure license_key == install_id
    _migrate_legacy_flag()
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
    set_secret("license_key", license_key.strip())
    return refresh()


@lru_cache(maxsize=4)
def _public_key(pem: str):
    from cryptography.hazmat.primitives import serialization

    return serialization.load_pem_public_key(pem.encode())


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

        public_key = _public_key(LICENSE_PUBLIC_KEY_PEM)
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
    """Fetch this install's signed license from the license server and store it (only if its
    signature checks out). A definitive "no license" (404) clears it; a server error or no network
    leaves what is stored, so a paying customer never loses Pro because of an outage."""
    _sync_install_id_key()  # after checkout: ensure we validate the install_id
    install = _this_install_id()
    key = get_secret("license_key") or install  # the key IS the install id
    if not key:
        return status()
    try:
        resp = httpx.get(f"{LICENSE_SERVER_URL}/license/{key}", timeout=10)
    except httpx.HTTPError as exc:
        log.warning("License server unreachable: %s", exc)
        return status()
    if resp.status_code == 404:
        set_setting("license_signed", None)
        set_setting("license_status", {"valid": False, "checked_at": time.time()})
        return status()
    if resp.status_code != 200:
        log.warning("License server answered %s; keeping the stored license", resp.status_code)
        return status()
    try:
        data = resp.json()
    except ValueError:
        return status()
    if not data.get("error") and _verify_signed_license(data, key):
        # Store exactly what the server signed (not the portal token, which is not part of it)
        set_setting("license_signed", {"payload": data["payload"], "signature": data["signature"]})
        set_setting("license_status", {"valid": True, "checked_at": time.time()})
        # Cache the fresh portal token the server mints on each lookup; the
        # billing-portal call presents it to prove ownership of this install.
        if data.get("portal_token"):
            try:
                set_secret("portal_token", data["portal_token"])
            except Exception as exc:  # keychain unavailable — non-fatal
                log.warning("Could not store portal token: %s", exc)
    else:
        log.warning("License response failed verification; ignoring it")
    return status()
