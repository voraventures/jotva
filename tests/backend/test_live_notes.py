"""Live-writing notes: the AI's text is streamed and announced to the app as it
grows, with a one-piece fallback for servers that can't stream. The AI client
and the event hub are faked; no network is used."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

os.environ['JOTVA_DATA_DIR'] = tempfile.mkdtemp(prefix='jotva-live-notes-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import anthropic
import httpx
import pytest
from app.config import ensure_dirs
from app.db import set_setting
from app.services import notes

ensure_dirs()


def delta(text):
    return NS(type="content_block_delta", delta=NS(type="text_delta", text=text))


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(notes.hub, "emit", lambda name, data: sent.append((name, data)))
    set_setting("ai_provider", "anthropic")
    return sent


def use_client(monkeypatch, create):
    monkeypatch.setattr(notes, "get_client", lambda: NS(messages=NS(create=create)))


def test_notes_stream_to_the_app_as_they_are_written(monkeypatch, events):
    def create(stream=False, **kw):
        assert stream is True
        return iter([NS(type="message_start"), delta("## Summary\n"), delta("Pricing "), delta("agreed.")])
    use_client(monkeypatch, create)
    live = notes._LiveNotes("m1", every=0)
    text = notes._complete("sys", "transcript", 100, on_text=live)
    assert text == "## Summary\nPricing agreed."
    texts = [d["text"] for name, d in events if name == "notes_delta"]
    assert texts == ["## Summary\n", "## Summary\nPricing ", "## Summary\nPricing agreed."]


def test_falls_back_to_one_piece_when_the_server_cannot_stream(monkeypatch, events):
    calls = []
    def create(stream=False, **kw):
        calls.append(stream)
        if stream:
            req = httpx.Request("POST", "https://license.example/api/ai/v1/messages")
            raise anthropic.BadRequestError("no streaming", response=httpx.Response(400, request=req), body=None)
        return NS(content=[NS(type="text", text="## Summary\nDone.")])
    use_client(monkeypatch, create)
    text = notes._complete("sys", "transcript", 100, on_text=notes._LiveNotes("m1", every=0))
    assert text == "## Summary\nDone." and calls == [True, False]
    assert events[-1] == ("notes_delta", {"meeting_id": "m1", "text": "## Summary\nDone.", "final": False})


def test_updates_are_throttled_but_the_final_text_always_goes_out(events):
    live = notes._LiveNotes("m1", every=60)
    live("a")
    live("ab")
    live("abc", final=True)
    assert [d["text"] for _, d in events] == ["a", "abc"] and events[-1][1]["final"] is True
