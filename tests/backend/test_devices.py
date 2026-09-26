"""Saved microphones are matched by name, because device indexes shift as
devices are plugged in and out. No real audio hardware is touched."""
import os
import sys
import tempfile
from pathlib import Path

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-device-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.services import recorder

DEVICES = [{"index": 0, "name": "BlackHole 2ch"}, {"index": 3, "name": "EarPods Microphone"}]


def test_saved_mic_follows_its_name_to_a_new_index(monkeypatch):
    monkeypatch.setattr(recorder, "list_input_devices", lambda: DEVICES)
    assert recorder.saved_device(1, "EarPods Microphone") == 3


def test_missing_saved_mic_falls_back_to_system_default(monkeypatch):
    monkeypatch.setattr(recorder, "list_input_devices", lambda: DEVICES)
    assert recorder.saved_device(2, "USB Podcast Mic") is None


def test_choices_saved_before_names_were_stored_keep_their_index():
    assert recorder.saved_device(2, None) == 2
    assert recorder.saved_device(None, None) is None
