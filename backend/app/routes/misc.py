"""License, export, integrations, settings, secrets."""
import base64
import binascii
import re

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import (
    CLAUDE_MODEL,
    DEFAULT_AI_PROVIDER,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    LICENSE_SERVER_URL,
    is_safe_managed_path,
)
from ..db import get_db, get_setting, set_setting
from ..services import exporter, license as license_svc, model_catalog, notes as notes_svc
from ..services.integrations import SENDERS
from ..services.keychain import KNOWN_SECRETS, delete_secret, get_secret, secret_status, set_secret
from ..services.recorder import AUDIO_AVAILABLE
from ..services.transcriber import is_available as whisper_available

router = APIRouter(prefix="/api", tags=["misc"])


class LicenseKeyBody(BaseModel):
    license_key: str = Field(min_length=8, max_length=200)


class SecretBody(BaseModel):
    name: str = Field(max_length=60)
    value: str = Field(min_length=1, max_length=4000)


class SettingBody(BaseModel):
    key: str = Field(max_length=60)
    value: object = None


# Per-key validators (C6: never trust renderer input shape)
def _is_device(v):
    # 0-255: PortAudio device indices; 1000+: synthetic WASAPI loopback indices
    return v is None or (isinstance(v, int) and 0 <= v < 2048)


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")


def _is_model_id(v):
    return isinstance(v, str) and bool(_MODEL_ID_RE.match(v))


def _is_word_list(v):
    return (
        isinstance(v, list)
        and len(v) <= 100
        and all(isinstance(w, str) and 0 < len(w) <= 60 for w in v)
    )


SETTING_VALIDATORS = {
    "speaker_identification": lambda v: isinstance(v, bool),
    "mcp_enabled": lambda v: isinstance(v, bool),
    "theme": lambda v: v in ("default", "dark", "purple", "navy", "warm", "neon"),
    "recording_mode": lambda v: v in ("all", "confirm_30s", "manual", "off"),
    "mic_device": _is_device,
    "system_device": _is_device,
    "whisper_model": lambda v: v in ("tiny", "base", "small", "medium", "large-v3"),
    # Any id from the provider's live model list; ids change without app releases,
    # so only the shape is checked.
    "claude_model": lambda v: _is_model_id(v),
    "ai_provider": lambda v: v in ("anthropic", "openai", "google"),
    "ai_quality": lambda v: v in ("standard", "pro"),
    "live_notes_enabled": lambda v: isinstance(v, bool),
    "openai_model": lambda v: _is_model_id(v),
    "gemini_model": lambda v: _is_model_id(v),
    "apple_calendar_enabled": lambda v: isinstance(v, bool),
    "auto_launch": lambda v: isinstance(v, bool),
    "list_panel_width": lambda v: isinstance(v, (int, float)) and 240 <= v <= 480,
    "coach_enabled": lambda v: isinstance(v, bool),
    "redact_words": _is_word_list,
    "exclude_patterns": _is_word_list,
    "retention_days": lambda v: isinstance(v, int) and 0 <= v <= 3650,
    "default_template": lambda v: isinstance(v, str) and len(v) <= 64,
    "font_size": lambda v: v in ("small", "medium", "large"),
    "reduce_motion": lambda v: isinstance(v, bool),
}


# ---------- license ----------
@router.get("/license/status")
def license_status():
    return license_svc.status()


@router.post("/license/activate")
def license_activate(body: LicenseKeyBody):
    try:
        return license_svc.activate(body.license_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/license/refresh")
def license_refresh():
    return license_svc.refresh()


@router.get("/install-id")
def install_id():
    from .workspace import _install_id

    return {"install_id": _install_id()}


@router.get("/license/portal-url")
def license_portal_url():
    from .workspace import _install_id

    install = _install_id()

    def _post(token):
        return httpx.post(
            f"{LICENSE_SERVER_URL}/portal",
            json={"install_id": install, "portal_token": token},
            timeout=10,
        )

    try:
        resp = _post(get_secret("portal_token"))
        # 401/403 => token missing or expired (24h TTL). Refresh the license,
        # which mints and caches a fresh portal token, then retry once.
        if resp.status_code in (401, 403):
            license_svc.refresh()
            resp = _post(get_secret("portal_token"))
    except httpx.HTTPError:
        return {"url": None, "error": "unavailable"}

    if resp.status_code == 404:
        return {"url": None, "error": "no_subscription"}
    if resp.status_code in (401, 403):
        return {"url": None, "error": "unauthorized"}
    if resp.status_code == 200:
        try:
            return {"url": resp.json().get("url")}
        except ValueError:
            return {"url": None, "error": "unavailable"}
    return {"url": None, "error": "unavailable"}


# ---------- integrations ----------
@router.get("/integrations/status")
def integrations_status():
    return {"providers": list(SENDERS.keys()), "secrets": secret_status()}


@router.post("/integrations/{provider}/send/{meeting_id}")
def send_to_integration(provider: str, meeting_id: str):
    license_svc.require_pro("integrations")
    sender = SENDERS.get(provider)
    if not sender:
        raise HTTPException(status_code=422, detail="Unknown integration")
    db = get_db()
    meeting = db.execute(
        "SELECT title FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()
    note = db.execute(
        "SELECT content FROM notes WHERE meeting_id=?", (meeting_id,)
    ).fetchone()
    if not meeting or not note:
        raise HTTPException(status_code=404, detail="Meeting notes not found")
    try:
        result = sender(meeting["title"], note["content"])
        return {"ok": True, "message": result}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        # Never leak third-party exception detail (C8)
        raise HTTPException(status_code=502, detail=f"{provider} request failed")


# ---------- secrets (write-only; values never readable back) ----------
@router.post("/secrets")
def save_secret(body: SecretBody):
    if body.name not in KNOWN_SECRETS:
        raise HTTPException(status_code=422, detail="Unknown secret name")
    if body.name in ("anthropic_api_key", "openai_api_key", "google_api_key"):
        license_svc.require_pro("own_key")
    try:
        set_secret(body.name, body.value)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True}


@router.delete("/secrets/{name}")
def remove_secret(name: str):
    if name not in KNOWN_SECRETS:
        raise HTTPException(status_code=422, detail="Unknown secret name")
    delete_secret(name)
    return {"ok": True}


# ---------- settings ----------
@router.get("/settings")
def get_settings():
    return {
        "speaker_identification": get_setting("speaker_identification", True),
        "theme": get_setting("theme", "default"),
        "recording_mode": get_setting("recording_mode", "confirm_30s"),
        "mic_device": get_setting("mic_device"),
        "system_device": get_setting("system_device"),
        "whisper_model": get_setting("whisper_model", "base"),
        "claude_model": get_setting("claude_model", CLAUDE_MODEL),
        "ai_provider": get_setting("ai_provider", DEFAULT_AI_PROVIDER),
        "ai_quality": "pro" if notes_svc.bundled_tier() == notes_svc.TIER_PRO else "standard",
        "live_notes_enabled": get_setting("live_notes_enabled", True),
        # Set when a saved model disappeared and generation switched to the
        # recommended one; the UI shows it once, then clears it.
        "model_notice": get_setting("model_notice"),
        "openai_model": get_setting("openai_model", DEFAULT_OPENAI_MODEL),
        "gemini_model": get_setting("gemini_model", DEFAULT_GEMINI_MODEL),
        "apple_calendar_enabled": get_setting("apple_calendar_enabled", False),
        "auto_launch": get_setting("auto_launch", False),
        "list_panel_width": get_setting("list_panel_width", 308),
        "coach_enabled": get_setting("coach_enabled", True),
        "redact_words": get_setting("redact_words", []),
        "exclude_patterns": get_setting("exclude_patterns", []),
        "retention_days": get_setting("retention_days", 0),
        "default_template": get_setting("default_template", "builtin-default"),
        "font_size": get_setting("font_size", "medium"),
        "reduce_motion": get_setting("reduce_motion", False),
        "mcp_enabled": get_setting("mcp_enabled", False),
    }


@router.get("/ai/models")
def ai_models(provider: str):
    """Models the user's own key can use for a provider (live, cached ~6h), or a
    built-in fallback list when there is no key or the provider can't be reached."""
    if provider not in model_catalog.PROVIDERS:
        raise HTTPException(status_code=422, detail="Unknown provider")
    models, _live = model_catalog.list_models(provider)
    return models


@router.delete("/ai/model-notice")
def dismiss_model_notice():
    set_setting("model_notice", None)
    return {"ok": True}


# Setting values only Pro may turn on (turning them off is always allowed).
_PRO_SETTING_VALUES = {
    ("mcp_enabled", True): "mcp",
    ("recording_mode", "all"): "auto_record",
    ("ai_quality", "pro"): "higher_quality",
    ("live_notes_enabled", True): "live_notes",
    ("ai_provider", "openai"): "own_key",
    ("ai_provider", "google"): "own_key",
}


@router.post("/settings")
def save_setting(body: SettingBody):
    validator = SETTING_VALIDATORS.get(body.key)
    if validator is None:
        raise HTTPException(status_code=422, detail="Unknown setting")
    if not validator(body.value):
        raise HTTPException(status_code=422, detail="Invalid value for setting")
    pro_only = _PRO_SETTING_VALUES.get((body.key, body.value if isinstance(body.value, (str, bool)) else None))
    if pro_only:
        license_svc.require_pro(pro_only)
    set_setting(body.key, body.value)
    if body.key in ("mic_device", "system_device"):
        # Remember the device by name too: indexes shift as devices come and go.
        from ..services.recorder import list_input_devices

        name = next((d["name"] for d in list_input_devices() if d["index"] == body.value), None)
        set_setting(f"{body.key}_name", name)
    if body.key == 'speaker_identification':
        from ..services.speaker_capture import capture
        capture.boundary()
    return {"ok": True}


class UserNameBody(BaseModel):
    name: str = Field(max_length=100)


@router.get("/settings/user-name")
def get_user_name():
    return {"user_name": get_setting("user_name", "")}


@router.post("/settings/user-name")
def set_user_name(body: UserNameBody):
    name = body.name.strip()
    if not (1 <= len(name) <= 100):
        raise HTTPException(status_code=422, detail="Name must be 1-100 characters")
    set_setting("user_name", name)
    return {"ok": True, "user_name": name}


# ---------- profile photo ----------
# The renderer crops/resizes the photo to 256px and re-encodes it (which also drops
# EXIF/GPS metadata); we still verify it really is a small JPEG/PNG/WebP before storing.
_AVATAR_RE = re.compile(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/]+={0,2})$")
_AVATAR_MAGIC = {"jpeg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n", "webp": b"RIFF"}
AVATAR_MAX_BYTES = 256 * 1024


class AvatarBody(BaseModel):
    image: str = Field(max_length=360_000)


@router.get("/settings/avatar")
def get_avatar():
    return {"avatar": get_setting("user_avatar")}


@router.post("/settings/avatar")
def set_avatar(body: AvatarBody):
    match = _AVATAR_RE.match(body.image)
    if not match:
        raise HTTPException(status_code=422, detail="Photo must be a JPEG, PNG or WebP image")
    kind, payload = match.groups()
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="Photo data is corrupted")
    valid = raw.startswith(_AVATAR_MAGIC[kind]) and (kind != "webp" or raw[8:12] == b"WEBP")
    if not valid or len(raw) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=422, detail="Photo is not a valid image or is too large")
    set_setting("user_avatar", body.image)
    return {"ok": True}


@router.delete("/settings/avatar")
def delete_avatar():
    set_setting("user_avatar", None)
    return {"ok": True}


# ---------- templates ----------
class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    body: str = Field(min_length=10, max_length=8000)


@router.get("/templates")
def list_templates_route():
    from ..services.templates import list_templates

    return list_templates()


@router.post("/templates")
def create_template_route(body: TemplateBody):
    from ..services.templates import create_template

    license_svc.require_pro("templates")
    return create_template(body.name.strip(), body.description.strip(), body.body)


@router.patch("/templates/{template_id}")
def update_template_route(template_id: str, body: TemplateBody):
    from ..services.templates import update_template

    license_svc.require_pro("templates")
    if not update_template(template_id, body.name.strip(), body.description.strip(), body.body):
        raise HTTPException(status_code=404, detail="Template not found or built-in")
    return {"ok": True}


@router.delete("/templates/{template_id}")
def delete_template_route(template_id: str):
    from ..services.templates import delete_template

    if not delete_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found or built-in")
    return {"ok": True}


# ---------- semantic knowledge search ----------
class AskBody(BaseModel):
    query: str = Field(min_length=3, max_length=300)


@router.post("/search/ask")
def search_ask(body: AskBody):
    from ..services.ai import semantic_search

    license_svc.require_pro("ask_all")
    try:
        return {"results": semantic_search(body.query.strip())}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- export pack ----------
@router.post("/export/pack/actions_csv")
def export_pack_actions():
    return {"path": str(exporter.export_actions_csv())}


@router.post("/export/pack/timeline_pdf")
def export_pack_timeline():
    return {"path": str(exporter.export_timeline_pdf())}


@router.get("/export/{meeting_id}/slack")
def export_slack(meeting_id: str):
    import json as _json

    db = get_db()
    meeting = db.execute(
        "SELECT title FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()
    note = db.execute(
        "SELECT sections FROM notes WHERE meeting_id=?", (meeting_id,)
    ).fetchone()
    if not meeting or not note:
        raise HTTPException(status_code=404, detail="Meeting notes not found")
    sections = _json.loads(note["sections"] or "{}")
    return {"text": exporter.slack_digest(meeting["title"], sections)}


# Declared before the generic /{fmt} route so "my-actions" matches here first.
@router.post("/export/{meeting_id}/my-actions")
def export_my_actions(meeting_id: str):
    user_name = get_setting("user_name", "")
    if not user_name:
        raise HTTPException(status_code=400, detail="Set your name in Settings first")
    return {"path": str(exporter.export_my_actions_pdf(meeting_id, user_name))}


# ---------- export ----------
@router.post("/export/{meeting_id}/{fmt}")
def export(meeting_id: str, fmt: str):
    if fmt not in exporter.EXPORTERS:
        raise HTTPException(status_code=422, detail="Format must be pdf, markdown, or text")
    db = get_db()
    meeting = db.execute(
        "SELECT title FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()
    note = db.execute(
        "SELECT content FROM notes WHERE meeting_id=?", (meeting_id,)
    ).fetchone()
    if not meeting or not note:
        raise HTTPException(status_code=404, detail="Meeting notes not found")
    path = exporter.EXPORTERS[fmt](meeting["title"], note["content"])
    return {"path": str(path)}



# ---------- encrypted vault ----------
class VaultExportBody(BaseModel):
    password: str = Field(min_length=8, max_length=200)
    include_audio: bool = False


class VaultImportBody(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    password: str = Field(min_length=8, max_length=200)


@router.post("/vault/export")
def vault_export(body: VaultExportBody):
    from ..services.vault import export_vault

    try:
        return {"path": export_vault(body.password, body.include_audio)}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/vault/import")
def vault_import(body: VaultImportBody):
    from ..config import is_safe_managed_path
    from ..services.vault import import_vault

    # only vaults inside our own data dir (e.g. exports/) may be restored,
    # keeping the path surface sandboxed (C6)
    if not is_safe_managed_path(body.path) or not body.path.endswith(".aguavault"):
        raise HTTPException(
            status_code=422,
            detail="Vault file must be an .aguavault inside the Jotva data folder",
        )
    try:
        count = import_vault(body.path, body.password)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Vault file not found")
    return {"ok": True, "restored": count, "restart_recommended": True}


# ---------- health ----------
@router.get("/health")
def health():
    return {
        "ok": True,
        "audio": AUDIO_AVAILABLE,
        "whisper": whisper_available(),
        "claude_configured": notes_svc.is_configured(),
    }
