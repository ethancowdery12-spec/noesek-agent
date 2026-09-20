"""STT ingest: offline transcription path + webhook voice-note flow."""

import pytest

from sqlalchemy import delete

from noesek import stt
from noesek.channels import whatsapp
from noesek.db import Conversation, Session, init_db, migrate


@pytest.fixture(autouse=True)
def _authorize(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALLOWED_USERS", "15551234567")


@pytest.fixture(autouse=True)
async def _clean():
    yield
    try:
        async with Session() as s:
            await s.execute(delete(Conversation))
            await s.commit()
    except Exception:
        pass


def test_available_requires_ffmpeg_vosk_model(monkeypatch):
    monkeypatch.setattr(stt.shutil, "which", lambda b: "/usr/bin/ffmpeg" if b == "ffmpeg" else None)
    monkeypatch.delenv(stt.MODEL_ENV, raising=False)
    assert stt.available() is False
    monkeypatch.setenv(stt.MODEL_ENV, "/opt/model")
    import importlib.util
    assert stt.available() is (importlib.util.find_spec("vosk") is not None)


@pytest.mark.asyncio
async def test_transcribe_rejects_empty_and_oversize():
    with pytest.raises(stt.STTError):
        await stt.transcribe(b"")
    with pytest.raises(stt.STTError):
        await stt.transcribe(b"x" * (stt.MAX_BYTES + 1))


@pytest.mark.asyncio
async def test_transcribe_full_path_stubbed(monkeypatch, tmp_path):
    monkeypatch.setattr(stt.shutil, "which", lambda b: "/usr/bin/ffmpeg")
    monkeypatch.setenv(stt.MODEL_ENV, "/opt/model")

    class FakeProc:
        returncode = 0
        async def communicate(self): return (b"\x00\x01" * 800, b"")

    async def fake_exec(*a, **k): return FakeProc()
    monkeypatch.setattr(stt.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(stt, "_recognize", lambda pcm: "hello ethan")

    assert await stt.transcribe(b"oggbytes", "audio/ogg") == "hello ethan"


@pytest.mark.asyncio
async def test_recognize_missing_model(monkeypatch):
    monkeypatch.delenv(stt.MODEL_ENV, raising=False)
    import importlib.util
    if importlib.util.find_spec("vosk") is None:
        with pytest.raises(stt.STTError, match="vosk is not installed"):
            stt._recognize(b"\x00" * 100)
    else:
        with pytest.raises(stt.STTError, match="not set"):
            stt._recognize(b"\x00" * 100)


@pytest.mark.asyncio
async def test_webhook_voice_note_transcribed(monkeypatch, tmp_path):
    await init_db(); await migrate()
    monkeypatch.setattr(whatsapp.settings, "whatsapp_access_token", "tok")
    monkeypatch.setattr(whatsapp.settings, "meta_app_secret", "")

    async def fake_fetch(media_id):
        return b"oggbytes", "audio/ogg"

    async def fake_transcribe(data, mime):
        return "ship it"

    monkeypatch.setattr(whatsapp, "_fetch_media", fake_fetch)
    import noesek.stt as stt_mod
    monkeypatch.setattr(stt_mod, "transcribe", fake_transcribe)

    handled = []
    class FakeResult:
        text = "on it"
    async def fake_handle(cid, text, external_id=None):
        handled.append(text)
        return FakeResult()
    monkeypatch.setattr(whatsapp.controller, "handle", fake_handle)

    replies = []
    async def fake_send(to, text):
        replies.append(text)
        return {"sent": 1}
    monkeypatch.setattr(whatsapp, "send_text", fake_send)

    from fastapi.testclient import TestClient
    from noesek.main import app
    client = TestClient(app)
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "15551234567", "id": "wamid-1", "type": "voice",
         "voice": {"id": "media-1", "mime_type": "audio/ogg"}}]}}]}]}
    out = client.post("/webhooks/whatsapp", json=payload)
    assert out.status_code == 200
    assert handled == ["[voice note] ship it"]
    assert replies == ["on it"]


@pytest.mark.asyncio
async def test_webhook_voice_note_fallback(monkeypatch):
    await init_db(); await migrate()
    monkeypatch.setattr(whatsapp.settings, "meta_app_secret", "")

    async def fake_transcribe_inbound(media):
        return None
    monkeypatch.setattr(whatsapp, "_transcribe_inbound", fake_transcribe_inbound)

    replies = []
    async def fake_send(to, text):
        replies.append(text)
        return {"sent": 1}
    monkeypatch.setattr(whatsapp, "send_text", fake_send)

    from fastapi.testclient import TestClient
    from noesek.main import app
    client = TestClient(app)
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "15551234567", "id": "wamid-2", "type": "voice",
         "voice": {"id": "media-2"}}]}}]}]}
    out = client.post("/webhooks/whatsapp", json=payload)
    assert out.status_code == 200
    assert replies and "couldn't transcribe" in replies[0]
