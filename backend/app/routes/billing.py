"""Upgrade to Pro: asks the license server for a Stripe checkout link for this
install. Goes through the backend so it follows LICENSE_SERVER_URL (and its dev
override) instead of a URL hard-coded in the UI."""
import httpx
from fastapi import APIRouter, HTTPException

from ..config import LICENSE_SERVER_URL

router = APIRouter(prefix="/api/license", tags=["billing"])


@router.post("/checkout")
def checkout():
    from .workspace import _install_id

    try:
        resp = httpx.post(f"{LICENSE_SERVER_URL}/checkout", json={"install_id": _install_id()}, timeout=15)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Couldn't reach the Jotva server. Check your connection and try again.")
    url = resp.json().get("url") if resp.status_code == 200 else None
    if not isinstance(url, str) or not url.startswith("https://"):
        raise HTTPException(status_code=502, detail=f"Checkout isn't available right now ({resp.status_code}).")
    return {"url": url}
