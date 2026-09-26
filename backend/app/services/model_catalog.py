"""Live model lists for bring-your-own-key AI providers.

With the user's own key we ask each provider which models that key can use
(Anthropic /v1/models, OpenAI /v1/models, Gemini models.list), cache the answer
in memory for a few hours, and fall back to a small hard-coded list when there
is no key or the fetch fails. Nothing here is persisted, and keys never leave
the provider SDK calls.
"""
import hashlib
import logging
import re
import threading
import time

from ..config import CLAUDE_MODEL, DEFAULT_GEMINI_MODEL, DEFAULT_OPENAI_MODEL
from .keychain import get_secret

log = logging.getLogger("jotva.models")

PROVIDERS = ("anthropic", "openai", "google")
_KEY_NAMES = {"anthropic": "anthropic_api_key", "openai": "openai_api_key", "google": "google_api_key"}

CACHE_TTL_SEC = 6 * 3600
# After a failed fetch, serve the fallback for a while instead of retrying the
# network on every call (generation checks the catalog too).
FAILURE_TTL_SEC = 10 * 60
FETCH_TIMEOUT_SEC = 10

# Used when there is no key or the provider can't be reached. The first entry
# is the recommended default.
FALLBACK = {
    "anthropic": [
        ("claude-haiku-4-5", "Claude Haiku 4.5"),
        ("claude-sonnet-5", "Claude Sonnet 5"),
        ("claude-opus-5", "Claude Opus 5"),
    ],
    "openai": [
        ("gpt-4o", "GPT-4o"),
        ("gpt-4o-mini", "GPT-4o mini"),
        ("o3-mini", "o3 mini"),
    ],
    "google": [
        ("gemini-2.0-flash", "Gemini 2.0 Flash"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ],
}

# Recommended default per provider: the first of these the live list contains,
# else the first model listed.
_PREFERRED = {
    "anthropic": ["claude-haiku-4-5", CLAUDE_MODEL],
    "openai": [DEFAULT_OPENAI_MODEL, "gpt-4o", "gpt-4o-mini"],
    "google": [DEFAULT_GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.0-flash"],
}

_OPENAI_EXCLUDE = (
    "embedding", "audio", "image", "tts", "whisper", "moderation", "realtime",
    "transcribe", "search", "dall-e", "instruct", "codex", "computer-use",
)
_GOOGLE_EXCLUDE = ("embedding", "aqa", "tts", "image")
_DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{8}$")
_SNAPSHOT_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}|-\d{8}")

_lock = threading.Lock()
# provider -> (expires_at, key_fingerprint, models or None when the fetch failed)
_cache: dict[str, tuple[float, str, list[dict] | None]] = {}


def _fingerprint(key: str) -> str:
    # Lets a changed key invalidate the cache without keeping the key itself around.
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _fetch_anthropic(key: str) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=key, timeout=FETCH_TIMEOUT_SEC, max_retries=1)
    # The SDK pages through has_more automatically. Newest first.
    return [{"id": m.id, "name": m.display_name or m.id} for m in client.models.list(limit=1000)]


def _is_openai_text_model(model_id: str) -> bool:
    mid = model_id.lower()
    if not (mid.startswith("gpt-") or re.match(r"^o\d", mid) or mid.startswith("chatgpt-")):
        return False
    return not any(bad in mid for bad in _OPENAI_EXCLUDE) and not _DATED_SNAPSHOT.search(mid)


def _fetch_openai(key: str) -> list[dict]:
    import openai

    client = openai.OpenAI(api_key=key, timeout=FETCH_TIMEOUT_SEC, max_retries=1)
    models = [m for m in client.models.list() if _is_openai_text_model(m.id)]
    models.sort(key=lambda m: getattr(m, "created", 0) or 0, reverse=True)
    return [{"id": m.id, "name": m.id} for m in models]


def _fetch_google(key: str) -> list[dict]:
    import google.generativeai as genai

    genai.configure(api_key=key)
    out = []
    for m in genai.list_models(page_size=1000, request_options={"timeout": FETCH_TIMEOUT_SEC}):
        if "generateContent" not in (m.supported_generation_methods or []):
            continue
        model_id = m.name.removeprefix("models/")
        if not model_id.startswith("gemini") or any(bad in model_id for bad in _GOOGLE_EXCLUDE):
            continue
        out.append({"id": model_id, "name": m.display_name or model_id})
    return out


_FETCHERS = {"anthropic": _fetch_anthropic, "openai": _fetch_openai, "google": _fetch_google}


def _with_recommended(provider: str, models: list[dict]) -> list[dict]:
    ids = [m["id"] for m in models]
    rec = next((hit for p in _PREFERRED[provider] if (hit := _listed_as(p, ids))), ids[0] if ids else None)
    out = [{"id": m["id"], "name": m["name"], "recommended": m["id"] == rec} for m in models]
    # Recommended first, otherwise keep the provider's order.
    out.sort(key=lambda m: not m["recommended"])
    return out


def _fallback(provider: str) -> list[dict]:
    return _with_recommended(provider, [{"id": i, "name": n} for i, n in FALLBACK[provider]])


def _live(provider: str) -> list[dict] | None:
    """The provider's live list for the user's key (cached), or None if unavailable."""
    key = get_secret(_KEY_NAMES[provider])
    if not key:
        return None
    fp = _fingerprint(key)
    now = time.time()
    with _lock:
        hit = _cache.get(provider)
        if hit and hit[0] > now and hit[1] == fp:
            return hit[2]
    try:
        models = _FETCHERS[provider](key) or None
    except Exception as exc:
        # Type only: provider exception text can echo request details.
        log.warning("Model list fetch failed for %s: %s", provider, type(exc).__name__)
        models = None
    ttl = CACHE_TTL_SEC if models else FAILURE_TTL_SEC
    with _lock:
        _cache[provider] = (now + ttl, fp, models)
    return models


def list_models(provider: str) -> tuple[list[dict], bool]:
    """([{id, name, recommended}], is_live) for a provider."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    live = _live(provider)
    if live:
        return _with_recommended(provider, live), True
    return _fallback(provider), False


def recommended(provider: str) -> str:
    models, _ = list_models(provider)
    return next(m["id"] for m in models if m["recommended"])


def is_listed(model_id: str, ids) -> bool:
    """True if `model_id` is in the list, or the list has a dated snapshot of it
    (Anthropic may list the alias "claude-haiku-4-5" only as "claude-haiku-4-5-20251001")."""
    return _listed_as(model_id, ids) is not None


def _listed_as(model_id: str, ids) -> str | None:
    """The listed id that serves `model_id` (itself or a dated snapshot of it)."""
    ids = list(ids)
    if model_id in ids:
        return model_id
    return next((i for i in ids if i.startswith(model_id)
                 and _SNAPSHOT_SUFFIX.fullmatch(i[len(model_id):])), None)


def check_saved(provider: str, saved: str) -> str | None:
    """If the provider's LIVE list is known and no longer has `saved`, return the
    recommended replacement; otherwise None. A fallback list is never treated as
    authoritative, so an offline check can't discard a valid choice."""
    live = _live(provider)
    if not live or is_listed(saved, (m["id"] for m in live)):
        return None
    return next(m["id"] for m in _with_recommended(provider, live) if m["recommended"])


def clear_cache() -> None:
    with _lock:
        _cache.clear()
