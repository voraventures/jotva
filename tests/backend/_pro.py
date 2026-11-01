"""Test helper: make the (isolated, throwaway) install Pro the legitimate way.

Pro is a license signed by the license server. Here a throwaway RSA key plays the server: the
app's public key is swapped for the test key's, and a license is signed for this install exactly
as the real server signs it (RSA-SHA256 over the canonical JSON payload). There is no unsigned
shortcut to call, which is the point."""
import base64
import json
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.db import set_setting
from app.services import license as license_svc

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # "an attacker's" key
TEST_PUBLIC_PEM = _KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def sign(payload: dict, key=None) -> dict:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = (key or _KEY).sign(canonical, padding.PKCS1v15(), hashes.SHA256())
    return {"payload": payload, "signature": base64.b64encode(sig).decode()}


def payload_for(install_id: str, days: float = 35, tier: str = "pro") -> dict:
    now = datetime.now(timezone.utc)
    return {"install_id": install_id, "tier": tier, "issued_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": (now + timedelta(days=days)).isoformat().replace("+00:00", "Z")}


def use_test_key():
    license_svc.LICENSE_PUBLIC_KEY_PEM = TEST_PUBLIC_PEM


def grant_pro(days: float = 35) -> dict:
    """Store a server-style signed Pro license for this install."""
    use_test_key()
    signed = sign(payload_for(license_svc._this_install_id(), days))
    set_setting("license_signed", signed)
    return signed


def revoke_pro():
    set_setting("license_signed", None)
