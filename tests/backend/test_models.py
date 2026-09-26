"""AI model selection: live BYOK model lists (provider calls faked, no network),
bundled-AI tier aliases, and the saved-model fallback notice."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-model-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import ensure_dirs
from app.db import get_db, get_setting, set_setting
from app.routes import misc
from app.services import license as license_svc, model_catalog, notes

ensure_dirs()
app = FastAPI()
app.include_router(misc.router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """Fake keychain + fake provider fetchers; never touch the real ones."""
    get_db().execute("DELETE FROM settings"); get_db().commit()
    model_catalog.clear_cache()
    keys = {}
    fake_get = lambda name: keys.get(name)
    monkeypatch.setattr(model_catalog, "get_secret", fake_get)
    monkeypatch.setattr(notes, "get_secret", fake_get)
    calls = {"anthropic": 0, "openai": 0, "google": 0}
    lists = {
        "anthropic": [{"id": "claude-sonnet-5", "name": "Claude Sonnet 5"},
                      {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"}],
        "openai": [{"id": "gpt-5-mini", "name": "gpt-5-mini"}, {"id": "gpt-4o", "name": "gpt-4o"}],
        "google": [{"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"}],
    }

    def fetcher(provider):
        def fetch(key):
            calls[provider] += 1
            if isinstance(lists[provider], Exception):
                raise lists[provider]
            return [dict(m) for m in lists[provider]]
        return fetch

    monkeypatch.setattr(model_catalog, "_FETCHERS", {p: fetcher(p) for p in calls})
    monkeypatch.setattr(license_svc, "is_pro", lambda: False)
    yield NS(keys=keys, calls=calls, lists=lists)
    model_catalog.clear_cache()


# ---------- GET /api/ai/models ----------

def test_no_key_returns_fallback_with_recommended_first(isolated):
    r = client.get("/api/ai/models", params={"provider": "anthropic"})
    assert r.status_code == 200
    models = r.json()
    assert models[0] == {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "recommended": True}
    assert sum(m["recommended"] for m in models) == 1
    assert isolated.calls["anthropic"] == 0  # no key, no network


def test_live_list_is_fetched_once_and_cached(isolated):
    isolated.keys["openai_api_key"] = "test-key-1"
    first = client.get("/api/ai/models", params={"provider": "openai"}).json()
    second = client.get("/api/ai/models", params={"provider": "openai"}).json()
    assert first == second
    assert [m["id"] for m in first] == ["gpt-4o", "gpt-5-mini"]  # recommended (default) first
    assert first[0]["recommended"] and not first[1]["recommended"]
    assert isolated.calls["openai"] == 1


def test_changed_key_invalidates_cache(isolated):
    isolated.keys["google_api_key"] = "test-key-1"
    client.get("/api/ai/models", params={"provider": "google"})
    isolated.keys["google_api_key"] = "test-key-2"
    client.get("/api/ai/models", params={"provider": "google"})
    assert isolated.calls["google"] == 2


def test_recommended_falls_back_to_first_live_model(isolated):
    isolated.keys["google_api_key"] = "test-key"
    models = client.get("/api/ai/models", params={"provider": "google"}).json()
    assert models == [{"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "recommended": True}]


def test_fetch_failure_serves_fallback(isolated):
    isolated.keys["anthropic_api_key"] = "test-key"
    isolated.lists["anthropic"] = RuntimeError("boom")
    models = client.get("/api/ai/models", params={"provider": "anthropic"}).json()
    assert [m["id"] for m in models] == [i for i, _ in model_catalog.FALLBACK["anthropic"]]
    client.get("/api/ai/models", params={"provider": "anthropic"})
    assert isolated.calls["anthropic"] == 1  # failure is cached briefly too


def test_unknown_provider_rejected():
    assert client.get("/api/ai/models", params={"provider": "nope"}).status_code == 422


def test_openai_filter_keeps_text_models_only():
    keep = ["gpt-4o", "gpt-5-mini", "o3-mini", "o4-mini", "chatgpt-4o-latest"]
    drop = ["text-embedding-3-large", "gpt-4o-audio-preview", "gpt-image-1", "tts-1", "whisper-1",
            "omni-moderation-latest", "gpt-4o-realtime-preview", "gpt-4o-2024-08-06", "dall-e-3",
            "gpt-4o-mini-transcribe", "davinci-002"]
    assert all(model_catalog._is_openai_text_model(m) for m in keep)
    assert not any(model_catalog._is_openai_text_model(m) for m in drop)


def test_is_listed_accepts_dated_snapshot_of_alias():
    ids = ["claude-haiku-4-5-20251001", "claude-sonnet-5"]
    assert model_catalog.is_listed("claude-haiku-4-5", ids)
    assert model_catalog.is_listed("claude-sonnet-5", ids)
    assert not model_catalog.is_listed("claude-haiku-4", ids)
    assert not model_catalog.is_listed("claude-opus-5", ids)


# ---------- settings validation ----------

@pytest.mark.parametrize("value", ["claude-opus-5", "gpt-5-mini", "gemini-2.5-flash", "models/gemini-x", "o3"])
def test_model_setting_accepts_any_provider_id(value):
    assert client.post("/api/settings", json={"key": "claude_model", "value": value}).status_code == 200


@pytest.mark.parametrize("value", ["", "a b", "x" * 101, "claude;rm", 42, None, "-leading"])
def test_model_setting_rejects_unsafe_values(value):
    assert client.post("/api/settings", json={"key": "claude_model", "value": value}).status_code == 422


def test_ai_quality_setting():
    assert client.post("/api/settings", json={"key": "ai_quality", "value": "pro"}).status_code == 200
    assert client.post("/api/settings", json={"key": "ai_quality", "value": "max"}).status_code == 422


# ---------- bundled tier aliases ----------

@pytest.fixture
def fake_claude(monkeypatch):
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return NS(content=[NS(type="text", text="## Summary\nok")])

    monkeypatch.setattr(notes, "get_client", lambda: NS(messages=NS(create=create)))
    set_setting("ai_provider", "anthropic")
    get_db().execute("INSERT OR IGNORE INTO meetings(id,title,started_at,status) "
                     "VALUES('m1','Sync','2026-09-26T10:00:00','ready')")
    get_db().commit()
    return sent


def test_bundled_default_sends_standard_tier(fake_claude):
    notes.generate_notes("m1", "Sync", "Maya: hello.", [])
    assert fake_claude["model"] == "jotva-standard"


def test_bundled_pro_quality_sends_pro_tier(fake_claude, monkeypatch):
    monkeypatch.setattr(license_svc, "is_pro", lambda: True)
    set_setting("ai_quality", "pro")
    notes.generate_notes("m1", "Sync", "Maya: hello.", [])
    assert fake_claude["model"] == "jotva-pro"


def test_free_user_never_gets_pro_tier(fake_claude):
    set_setting("ai_quality", "pro")
    notes.generate_notes("m1", "Sync", "Maya: hello.", [])
    assert fake_claude["model"] == "jotva-standard"


def test_legacy_sonnet_choice_maps_to_pro_tier(monkeypatch):
    monkeypatch.setattr(license_svc, "is_pro", lambda: True)
    set_setting("claude_model", "claude-sonnet-4-6")
    assert notes.current_model() == "jotva-pro"
    assert client.get("/api/settings").json()["ai_quality"] == "pro"


def test_own_key_sends_concrete_model(isolated, fake_claude):
    isolated.keys["anthropic_api_key"] = "test-key"
    set_setting("claude_model", "claude-sonnet-5")
    notes.generate_notes("m1", "Sync", "Maya: hello.", [])
    assert fake_claude["model"] == "claude-sonnet-5"
    assert get_setting("model_notice") is None


def test_retired_own_key_model_falls_back_with_one_time_notice(isolated, fake_claude):
    isolated.keys["anthropic_api_key"] = "test-key"
    set_setting("claude_model", "claude-opus-4-1")
    notes.generate_notes("m1", "Sync", "Maya: hello.", [])
    # Live list has haiku only as a dated snapshot; the alias still counts as present.
    assert fake_claude["model"] == "claude-haiku-4-5-20251001"
    assert get_setting("claude_model") == "claude-haiku-4-5-20251001"
    notice = client.get("/api/settings").json()["model_notice"]
    assert notice == {"provider": "anthropic", "from": "claude-opus-4-1", "to": "claude-haiku-4-5-20251001"}
    assert client.delete("/api/ai/model-notice").status_code == 200
    assert client.get("/api/settings").json()["model_notice"] is None


def test_offline_fallback_never_discards_saved_model(isolated):
    isolated.keys["openai_api_key"] = "test-key"
    isolated.lists["openai"] = RuntimeError("offline")
    set_setting("openai_model", "gpt-some-new-model")
    assert notes._model_for("openai") == "gpt-some-new-model"
    assert get_setting("model_notice") is None


def test_old_proxy_rejecting_tier_retries_with_concrete_model():
    import anthropic
    import httpx

    seen = []

    def create(**kwargs):
        seen.append(kwargs["model"])
        if kwargs["model"].startswith("jotva-"):
            req = httpx.Request("POST", "https://license.example/api/ai/v1/messages")
            raise anthropic.BadRequestError("Model not available", response=httpx.Response(400, request=req), body=None)
        return "ok"

    proxy = notes._ProxyClient(NS(messages=NS(create=create)))
    assert proxy.messages.create(model="jotva-pro", max_tokens=10, messages=[]) == "ok"
    assert seen == ["jotva-pro", "claude-sonnet-5"]
