"""Computer runtime: local chat channel maps chat_id -> session -> reply."""
from __future__ import annotations

import os
import sys
import types

import pytest


def make_app(monkeypatch, tmp_path):
    os.environ["NOESEK_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/t.db"
    os.environ.pop("DISPLAY", None)
    for mod in list(sys.modules):
        if mod.startswith("noesek"):
            del sys.modules[mod]
    import importlib

    config = importlib.import_module("noesek.config")
    importlib.reload(config)
    db = importlib.import_module("noesek.db")
    importlib.reload(db)
    server = importlib.import_module("noesek.computer.server")
    importlib.reload(server)
    return server


@pytest.mark.asyncio
async def test_chat_creates_session_and_replies(monkeypatch, tmp_path):
    server = make_app(monkeypatch, tmp_path)

    class FakeResult:
        text = "hello back"

    seen = {}

    async def fake_handle(cid, text, external_id=None):
        seen["cid"] = cid
        seen["text"] = text
        return FakeResult()

    monkeypatch.setattr(server, "get_controller", lambda: types.SimpleNamespace(handle=fake_handle))
    await server.init_db()
    await server.migrate()
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r1 = await c.post("/chat", json={"chat_id": "ethan-1", "text": "hi"})
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["reply"] == "hello back"
        assert body["chat_id"] == "ethan-1"
        # same chat_id -> same session
        r2 = await c.post("/chat", json={"chat_id": "ethan-1", "text": "again"})
        assert r2.json()["conversation_id"] == body["conversation_id"]
        # different chat_id -> different session
        r3 = await c.post("/chat", json={"chat_id": "ethan-2", "text": "hi"})
        assert r3.json()["conversation_id"] != body["conversation_id"]
        assert seen["text"] == "hi"


@pytest.mark.asyncio
async def test_chat_requires_fields(monkeypatch, tmp_path):
    server = make_app(monkeypatch, tmp_path)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        assert (await c.post("/chat", json={"chat_id": "", "text": "hi"})).status_code == 400
        assert (await c.post("/chat", json={"chat_id": "x", "text": "  "})).status_code == 400


@pytest.mark.asyncio
async def test_screenshot_503_without_display(monkeypatch, tmp_path):
    server = make_app(monkeypatch, tmp_path)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r = await c.get("/computer/screenshot")
        assert r.status_code == 503


@pytest.mark.asyncio
async def test_healthz(monkeypatch, tmp_path):
    server = make_app(monkeypatch, tmp_path)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r = await c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True
