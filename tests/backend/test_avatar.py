"""Profile photo endpoint validation. Isolated: temp data dir, no user data."""
import base64
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-avatar-tests-')
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

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64


def data_url(kind, raw):
    return f"data:image/{kind};base64," + base64.b64encode(raw).decode()


@pytest.fixture(autouse=True)
def clean():
    db = get_db(); db.execute("DELETE FROM settings"); db.commit()


@pytest.mark.parametrize("kind,raw", [("jpeg", JPEG), ("png", PNG), ("webp", WEBP)])
def test_accepts_real_images_and_round_trips(kind, raw):
    url = data_url(kind, raw)
    assert client.post("/api/settings/avatar", json={"image": url}).status_code == 200
    assert client.get("/api/settings/avatar").json() == {"avatar": url}


@pytest.mark.parametrize("image", [
    data_url("jpeg", PNG),                       # declared type doesn't match the bytes
    data_url("webp", b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 8),
    data_url("svg+xml", b"<svg onload=alert(1)>"),  # scriptable formats are refused
    "data:image/png;base64,@@@notbase64@@@",
    "https://example.com/me.png",
    data_url("jpeg", b"\xff\xd8\xff" + b"\x00" * (256 * 1024)),  # over the size cap
])
def test_rejects_invalid_images(image):
    assert client.post("/api/settings/avatar", json={"image": image}).status_code == 422
    assert client.get("/api/settings/avatar").json() == {"avatar": None}


def test_remove():
    client.post("/api/settings/avatar", json={"image": data_url("png", PNG)})
    assert client.delete("/api/settings/avatar").status_code == 200
    assert client.get("/api/settings/avatar").json() == {"avatar": None}
