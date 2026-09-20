"""Channel-native delivery: WhatsApp doc push, fallbacks, dry-run."""

import pytest

from sqlalchemy import delete

from noesek import filestore
from noesek.channels import whatsapp
from noesek.db import Conversation, Session, init_db, migrate
from noesek.tools.delivery import deliver_file


@pytest.fixture(autouse=True)
async def _clean():
    yield
    try:
        async with Session() as s:
            await s.execute(delete(Conversation))
            await s.commit()
    except Exception:
        pass  # shared dev DB not initialized in this process yet - nothing to clean


async def _conv(channel, ext):
    await init_db(); await migrate()
    async with Session() as s:
        c = Conversation(channel=channel, external_user_id=ext)
        s.add(c); await s.commit()
        return c.id


@pytest.mark.asyncio
async def test_send_document_uploads_then_sends(monkeypatch):
    monkeypatch.setattr(whatsapp.settings, "whatsapp_access_token", "tok")
    monkeypatch.setattr(whatsapp.settings, "whatsapp_phone_number_id", "pn1")
    calls = []

    class FakeResp:
        def __init__(self, payload): self._p = payload
        def raise_for_status(self): pass
        def json(self): return self._p

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, headers=None, data=None, files=None, json=None):
            calls.append({"url": url, "files": files, "json": json})
            if url.endswith("/media"):
                return FakeResp({"id": "media-9"})
            return FakeResp({"messages": [{"id": "wamid-1"}]})

    import httpx
    real = httpx.AsyncClient
    httpx.AsyncClient = FakeClient
    try:
        out = await whatsapp.send_document("15551234567", "report.md", b"# hi", "text/markdown", "report.md")
    finally:
        httpx.AsyncClient = real

    assert out["sent"] is True and out["media_id"] == "media-9"
    assert calls[0]["url"].endswith("/media") and calls[0]["files"]["file"][0] == "report.md"
    doc = calls[1]["json"]
    assert doc["type"] == "document" and doc["document"]["id"] == "media-9"
    assert doc["document"]["filename"] == "report.md" and doc["to"] == "15551234567"


@pytest.mark.asyncio
async def test_send_document_dry_run_without_creds(monkeypatch):
    monkeypatch.setattr(whatsapp.settings, "whatsapp_access_token", "")
    out = await whatsapp.send_document("1555", "a.txt", b"x")
    assert out["dry_run"] is True


@pytest.mark.asyncio
async def test_deliver_file_whatsapp(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path / "files"))
    cid = await _conv("whatsapp", "15551234567")

    async def fake_send(to, filename, data, mime, caption=""):
        return {"sent": True, "media_id": "m-1", "filename": filename}

    monkeypatch.setattr(whatsapp, "send_document", fake_send)
    note = await deliver_file(cid, "n.txt", b"hi", "text/plain")
    assert note == {"delivered": "whatsapp", "media_id": "m-1"}


@pytest.mark.asyncio
async def test_deliver_file_fallbacks(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path / "files"))
    local = await _conv("local", "ethan")
    assert await deliver_file(local, "n.txt", b"hi", "text/plain") is None

    wa = await _conv("whatsapp", "1555")

    async def boom(*a, **k):
        raise RuntimeError("graph down")

    monkeypatch.setattr(whatsapp, "send_document", boom)
    note = await deliver_file(wa, "n.txt", b"hi", "text/plain")
    assert note["delivered"] is None and "download link" in note["note"]


@pytest.mark.asyncio
async def test_create_file_delivers_on_whatsapp(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path / "files"))
    cid = await _conv("whatsapp", "15551234567")
    sent = []

    async def fake_send(to, filename, data, mime, caption=""):
        sent.append(filename)
        return {"sent": True, "media_id": "m-2", "filename": filename}

    monkeypatch.setattr(whatsapp, "send_document", fake_send)
    from noesek.tools.file_tools import CreateFileInput, create_file_handler
    out = await create_file_handler(cid)(CreateFileInput(name="todo.txt", content="- milk\n"))
    assert out["created"] is True and out["delivered"] == "whatsapp"
    assert sent == ["todo.txt"]
    assert filestore.read_file("todo.txt") == b"- milk\n"
