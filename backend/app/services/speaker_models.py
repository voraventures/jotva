"""Pinned local speaker models. No audio, identity, or telemetry is uploaded."""
import hashlib
import importlib.util
import os
import tarfile
import tempfile
import shutil
import threading
from pathlib import Path

import httpx

from ..config import DATA_DIR, secure_file
from ..events import hub

VERSION = "sherpa-onnx-1.13.7-pyannote3-eres2net-v1"
MODEL_DIR = DATA_DIR / "models" / "speakers-v1"
ASSETS = (
    ("segmentation.tar.bz2", "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2", "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488", 6958444),
    ("embedding.onnx", "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx", "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b", 39593761),
)
_lock = threading.Lock()
_cancel = threading.Event()
_state = {"state": "missing", "progress": 0}
MODEL_HASHES = {'segmentation.onnx': '220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079', 'embedding.onnx': ASSETS[1][2]}
_verified_signature = None


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(path):
    """Cheap content sample so a same-size rewrite is noticed even when mtime does not move."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(8192))
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size > 8192:
            f.seek(size - 8192)
            h.update(f.read(8192))
    return h.hexdigest()


def ready():
    global _verified_signature
    try:
        if (MODEL_DIR / 'verified').read_text() != VERSION:
            return False
        signature = tuple(
            (str(MODEL_DIR / p), (MODEL_DIR / p).stat().st_size, _fingerprint(MODEL_DIR / p))
            for p in MODEL_HASHES
        )
        if signature != _verified_signature:
            if not all(_digest(MODEL_DIR / p) == digest for p, digest in MODEL_HASHES.items()):
                return False
            _verified_signature = signature
        return True
    except OSError:
        return False


def status():
    with _lock:
        result = dict(_state)
    if result["state"] not in ("downloading", "error"):
        result["state"] = "ready" if ready() else "missing"
    return {**result, "runtime_available": importlib.util.find_spec("sherpa_onnx") is not None, "version": VERSION, "download_bytes": sum(a[3] for a in ASSETS)}


def _update(state, progress=0):
    with _lock:
        _state.update(state=state, progress=progress)
    hub.emit("speaker_models", {"state": state, "progress": progress})


def install():
    with _lock:
        if _state["state"] == "downloading":
            return
        _state.update(state="downloading", progress=0)
        _cancel.clear()
    threading.Thread(target=_download, daemon=True, name="speaker-model-download").start()


def cancel():
    _cancel.set()


def _download():
    try:
        MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="speaker-download-", dir=MODEL_DIR.parent) as tmp:
            tmp = Path(tmp)
            received = 0
            total = sum(a[3] for a in ASSETS)
            for name, url, expected_hash, expected_size in ASSETS:
                target = tmp / name
                count = 0
                with httpx.stream("GET", url, follow_redirects=True, timeout=30) as response:
                    response.raise_for_status()
                    with target.open("wb") as out:
                        for block in response.iter_bytes(256 * 1024):
                            if _cancel.is_set():
                                raise InterruptedError()
                            count += len(block)
                            if count > expected_size:
                                raise ValueError("Model size mismatch")
                            out.write(block)
                            received += len(block)
                            _update("downloading", received / total)
                if count != expected_size or _digest(target) != expected_hash:
                    raise ValueError("Model checksum mismatch")
            # Extract only specific regular files; never trust archive paths/symlinks.
            with tarfile.open(tmp / "segmentation.tar.bz2", "r:bz2") as archive:
                for source, target in (("model.onnx", "segmentation.onnx"), ("LICENSE", "segmentation.LICENSE")):
                    member = archive.getmember("sherpa-onnx-pyannote-segmentation-3-0/" + source)
                    if not member.isfile() or member.size > 50_000_000:
                        raise ValueError("Invalid model archive")
                    (tmp / target).write_bytes(archive.extractfile(member).read())
            if _cancel.is_set():
                raise InterruptedError()
            MODEL_DIR.mkdir(exist_ok=True)
            # A marker is published last; partial installation is never ready.
            (MODEL_DIR / "verified").unlink(missing_ok=True)
            for name in ("segmentation.onnx", "embedding.onnx", "segmentation.LICENSE"):
                secure_file(tmp / name)
                os.replace(tmp / name, MODEL_DIR / name)
            for notice in (Path(__file__).resolve().parents[1] / 'speaker_notices').glob('*.txt'):
                shutil.copyfile(notice, MODEL_DIR / notice.name)
                secure_file(MODEL_DIR / notice.name)
            (MODEL_DIR / "verified").write_text(VERSION)
            secure_file(MODEL_DIR / "verified")
        _update("ready", 1)
    except InterruptedError:
        _update("missing")
    except Exception:
        # Do not leak third-party URLs/exception payloads into UI or logs.
        _update("error")
