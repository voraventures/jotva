"""Pro cannot be faked locally: it is a license signed by the license server, verified every time.

Each test plays someone trying to get Pro without paying: editing the database, replaying an
old or someone else's license, tampering with a signed one, setting environment variables,
or calling the old developer endpoint. Isolated: temp data dir, throwaway signing keys."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-license-sec-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import ensure_dirs
from app.db import get_db, set_setting
from app.main import create_app
from app.services import license as license_svc
from _pro import _OTHER, TEST_PUBLIC_PEM, grant_pro, payload_for, revoke_pro, sign, use_test_key  # noqa: E402

ensure_dirs()


@pytest.fixture(autouse=True)
def clean():
    db = get_db(); db.execute("DELETE FROM settings"); db.commit()
    use_test_key()
    license_svc._migration_started = False
    yield


def iid():
    return license_svc._this_install_id()


# ---- nothing unsigned grants Pro ----

@pytest.mark.parametrize("flag", [
    {"valid": True, "dev": True},
    {"dev": True},
    {"valid": True, "checked_at": 9999999999},
    {"valid": True, "checked_at": 0, "dev": False},
])
def test_the_old_local_flags_grant_nothing(flag):
    set_setting("license_status", flag)
    assert license_svc.is_pro() is False
    assert license_svc.status()["tier"] == "free"
    assert license_svc.has_feature("live_notes") is False


def test_a_signed_license_for_this_install_grants_pro():
    grant_pro()
    assert license_svc.is_pro() is True
    assert license_svc.status()["tier"] == "pro"


def test_garbage_in_the_license_setting_is_just_free():
    for junk in ("pro", 1, True, [], {}, {"payload": {}}, {"payload": "x", "signature": "y"}):
        set_setting("license_signed", junk)
        assert license_svc.is_pro() is False


# ---- a real license can't be bent ----

def test_a_license_signed_with_someone_elses_key_is_rejected():
    set_setting("license_signed", sign(payload_for(iid()), key=_OTHER))
    assert license_svc.is_pro() is False


@pytest.mark.parametrize("change", [
    {"tier": "enterprise"},
    {"expires_at": "2099-01-01T00:00:00Z"},   # extending a short license
    {"install_id": "someone-else"},
])
def test_editing_any_field_of_a_signed_license_breaks_it(change):
    signed = grant_pro(days=1)
    signed["payload"].update(change)
    set_setting("license_signed", signed)
    assert license_svc.is_pro() is False


def test_an_expired_license_is_not_pro():
    set_setting("license_signed", sign(payload_for(iid(), days=-1)))
    assert license_svc.is_pro() is False


def test_a_license_issued_to_another_install_is_not_pro_here():
    set_setting("license_signed", sign(payload_for("0123456789abcdef0123456789abcdef")))
    assert license_svc.is_pro() is False


def test_a_license_with_no_expiry_is_rejected():
    payload = payload_for(iid()); del payload["expires_at"]
    set_setting("license_signed", sign(payload))
    assert license_svc.is_pro() is False


def test_revoking_returns_to_free():
    grant_pro(); assert license_svc.is_pro()
    revoke_pro(); assert license_svc.is_pro() is False


# ---- there is no developer back door ----

def test_the_dev_endpoint_does_not_exist_even_with_the_old_environment_flags(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true"); monkeypatch.setenv("JOTVA_DEV", "1"); monkeypatch.setenv("JOTVA_DEV_KEY", "letmein")
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any("/dev" in p for p in paths)
    assert TestClient(app).post("/api/dev/set-tier", json={"tier": "pro"}).status_code in (401, 403, 404)
    assert license_svc.is_pro() is False


def test_the_old_dev_license_key_no_longer_exists(monkeypatch):
    monkeypatch.setenv("JOTVA_DEV_KEY", "letmein")
    assert not hasattr(license_svc, "DEV_LICENSE_KEY") and not hasattr(license_svc, "set_tier")
    monkeypatch.setattr(license_svc, "set_secret", lambda k, v: None)
    monkeypatch.setattr(license_svc, "get_secret", lambda k: "letmein")
    monkeypatch.setattr(license_svc.httpx, "get", lambda *a, **k: httpx.Response(404, json={"code": "no_license"}))
    license_svc.activate("letmein")
    assert license_svc.is_pro() is False


# ---- refresh(): what gets stored, and what an outage can't take away ----

def _server(monkeypatch, response):
    monkeypatch.setattr(license_svc.httpx, "get", lambda *a, **k: response)
    monkeypatch.setattr(license_svc, "set_secret", lambda k, v: None)
    monkeypatch.setattr(license_svc, "get_secret", lambda k: iid())


def test_refresh_stores_the_signed_license_and_ignores_unsigned_servers(monkeypatch):
    good = sign(payload_for(iid()))
    _server(monkeypatch, httpx.Response(200, json={**good, "portal_token": "t"}))
    license_svc.refresh()
    assert license_svc.is_pro() is True
    assert set(json.loads(get_db().execute("SELECT value FROM settings WHERE key='license_signed'").fetchone()[0])) == {"payload", "signature"}
    revoke_pro()
    # a fake server that just says "valid" without a real signature is worthless
    _server(monkeypatch, httpx.Response(200, json={"valid": True, "tier": "pro", "payload": payload_for(iid()), "signature": "AAAA"}))
    license_svc.refresh()
    assert license_svc.is_pro() is False


def test_a_server_outage_never_takes_pro_away(monkeypatch):
    grant_pro()
    for response in (httpx.Response(500), httpx.Response(429), httpx.Response(503, json={"error": "down"})):
        _server(monkeypatch, response)
        license_svc.refresh()
        assert license_svc.is_pro() is True
    monkeypatch.setattr(license_svc.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    license_svc.refresh()
    assert license_svc.is_pro() is True


def test_a_definitive_no_license_removes_pro(monkeypatch):
    grant_pro()
    _server(monkeypatch, httpx.Response(404, json={"code": "no_license"}))
    license_svc.refresh()
    assert license_svc.is_pro() is False


# ---- upgrading from the old flag ----

def test_the_old_flag_is_cleared_and_the_signed_license_is_fetched_once(monkeypatch):
    calls = []
    monkeypatch.setattr(license_svc, "refresh", lambda: calls.append(1))
    set_setting("license_status", {"valid": True, "dev": True, "checked_at": 1})
    license_svc.status(); license_svc.status()
    import time; time.sleep(0.2)
    assert license_svc.is_pro() is False                       # the flag no longer counts
    assert json.loads(get_db().execute("SELECT value FROM settings WHERE key='license_status'").fetchone()[0])["valid"] is False
    assert calls == [1]                                         # one background fetch, not two
    # a free user has nothing to migrate
    license_svc._migration_started = False; calls.clear()
    set_setting("license_status", {"valid": False}); license_svc.status(); time.sleep(0.1)
    assert calls == []
