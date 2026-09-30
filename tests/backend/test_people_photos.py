"""People's photos endpoints. Isolated: temp data dir, no user data."""
import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-people-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import ensure_dirs
from app.db import get_db
from app.routes import misc

ensure_dirs()
app = FastAPI()
app.include_router(misc.router)
client = TestClient(app)

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()


@pytest.fixture(autouse=True)
def clean():
    db = get_db(); db.execute("DELETE FROM settings"); db.commit()


def test_add_list_and_remove_by_normalised_name():
    assert client.post("/api/people/photos", json={"name": "  Maya   Chen ", "image": JPEG}).json() == {"ok": True, "key": "maya chen"}
    assert client.get("/api/people/photos").json() == {"photos": {"maya chen": JPEG}}
    assert client.delete("/api/people/photos", params={"name": "MAYA CHEN"}).status_code == 200
    assert client.get("/api/people/photos").json() == {"photos": {}}


def test_email_keys_work():
    client.post("/api/people/photos", json={"name": "Sarah@Acme.com", "image": JPEG})
    assert "sarah@acme.com" in client.get("/api/people/photos").json()["photos"]


@pytest.mark.parametrize("image", ["data:image/gif;base64,R0lGOD", "data:image/jpeg;base64,!!!", "data:image/png;base64," + base64.b64encode(b"notapng").decode()])
def test_rejects_bad_images(image):
    assert client.post("/api/people/photos", json={"name": "Alex", "image": image}).status_code == 422
    assert client.get("/api/people/photos").json() == {"photos": {}}


def test_rejects_blank_names():
    assert client.post("/api/people/photos", json={"name": "   ", "image": JPEG}).status_code == 422


def test_limit(monkeypatch):
    monkeypatch.setattr(misc, "PEOPLE_PHOTOS_MAX", 2)
    for n in ("a", "b"):
        assert client.post("/api/people/photos", json={"name": n, "image": JPEG}).status_code == 200
    assert client.post("/api/people/photos", json={"name": "c", "image": JPEG}).status_code == 422
    assert client.post("/api/people/photos", json={"name": "a", "image": JPEG}).status_code == 200   # replacing is fine
