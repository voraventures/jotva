"""Connector error paths that used to surface as a generic 500, and the shared data directory."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["JOTVA_DATA_DIR"] = tempfile.mkdtemp(prefix="jotva-connector-tests-")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import ensure_dirs, resolve_data_dir
from app.routes import calendar

ensure_dirs()
app = FastAPI()
app.include_router(calendar.router)
client = TestClient(app)


def test_microsoft_connect_without_a_client_id_is_a_400():
    response = client.post("/api/calendar/microsoft/connect")
    assert response.status_code == 400
    assert "credentials.json" in response.json()["detail"]


def test_data_dir_follows_the_platform_and_keeps_a_legacy_database(tmp_path):
    home = tmp_path / "home"
    roaming = home / "AppData" / "Roaming"
    mac = resolve_data_dir(platform="darwin", home=home, legacy_has_db=False, standard_has_db=False)
    assert mac == home / "Library" / "Application Support" / "Jotva"

    fresh = resolve_data_dir(
        platform="win32", home=home, appdata=str(roaming), legacy_has_db=False, standard_has_db=False
    )
    assert fresh == roaming / "Jotva"

    legacy = resolve_data_dir(
        platform="win32", home=home, appdata=str(roaming), legacy_has_db=True, standard_has_db=False
    )
    assert legacy == home / "Library" / "Application Support" / "Jotva"

    both = resolve_data_dir(
        platform="win32", home=home, appdata=str(roaming), legacy_has_db=True, standard_has_db=True
    )
    assert both == roaming / "Jotva"

    linux = resolve_data_dir(
        platform="linux", home=home, xdg_config_home=str(home / ".config"), legacy_has_db=False, standard_has_db=False
    )
    assert linux == home / ".config" / "Jotva"

    assert resolve_data_dir(env="/tmp/explicit-jotva", platform="win32", home=home) == Path("/tmp/explicit-jotva")
