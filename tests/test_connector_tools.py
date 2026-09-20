"""Connector reads as controller tools: grant lookup by conversation, READ surface."""
import pytest

from noesek.db import Conversation, Session, init_db, migrate
from noesek import connectors
from noesek.connectors import google as gtool
from noesek.core.controller import Controller
from noesek.tools.connector_reads import ConnectorReadInput


@pytest.mark.asyncio
async def test_connector_tools_in_registry_and_grant_flow(monkeypatch, tmp_path):
    await init_db()
    await migrate()
    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    # connector_reads imported default_store by name - patch there too
    import noesek.tools.connector_reads as cr
    monkeypatch.setattr(cr, "default_store", lambda: store)

    async with Session() as s:
        conv = Conversation(channel="local", external_user_id="ethan-main")
        s.add(conv)
        await s.commit()
        cid = conv.id

    # handlers bind the read fn at registry build time - patch before building
    async def fake_messages(token, max_results):
        return [{"id": "m1", "from": "sam@x.com", "subject": "tennis?",
                 "date": "Sun, 20 Sep 2026 09:00:00 -0500", "snippet": "sat 3pm?"}]

    monkeypatch.setattr(gtool, "list_messages", fake_messages)

    registry = Controller(llm=object()).registry(cid)
    names = set(registry.names())
    assert {"gmail_read", "calendar_read", "github_notifications"} <= names

    # no grant yet -> actionable error, not a crash
    h = registry.get("gmail_read").handler
    out = await h(ConnectorReadInput())
    assert "not connected" in out["error"]

    # grant appears -> reads flow
    store.put("google", "ethan-main", "tok-g", ("gmail.readonly",))
    out = await h(ConnectorReadInput(max_results=3))
    assert out["count"] == 1 and out["items"][0]["subject"] == "tennis?"


@pytest.mark.asyncio
async def test_gmail_send_tool_external_risk_and_grant_flow(monkeypatch, tmp_path):
    await init_db()
    await migrate()
    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    import noesek.tools.connector_reads as cr
    monkeypatch.setattr(cr, "default_store", lambda: store)

    async with Session() as s:
        conv = Conversation(channel="local", external_user_id="ethan-main")
        s.add(conv)
        await s.commit()
        cid = conv.id

    sent_calls = []

    async def fake_send(token, to, subject, body):
        sent_calls.append((to, subject, body))
        return {"id": "msg-1", "thread_id": "thr-1"}

    monkeypatch.setattr(gtool, "send_message", fake_send)

    registry = Controller(llm=object()).registry(cid)
    spec = registry.get("gmail_send")
    assert spec is not None
    from noesek.core.types import Risk
    assert spec.risk is Risk.EXTERNAL  # approval contract gates every send

    from noesek.tools.connector_reads import GmailSendInput
    h = spec.handler

    # no grant -> actionable error, nothing sent
    out = await h(GmailSendInput(to="sam@x.com", subject="tennis", body="sat 3pm?"))
    assert "not connected" in out["error"] and not sent_calls

    # grant with send scope -> sends through the stub
    store.put("google", "ethan-main", "tok-g",
              ("gmail.readonly", "gmail.send"))
    out = await h(GmailSendInput(to="sam@x.com", subject="tennis", body="sat 3pm?"))
    assert out["sent"] is True and out["id"] == "msg-1"
    assert sent_calls == [("sam@x.com", "tennis", "sat 3pm?")]


@pytest.mark.asyncio
async def test_gmail_send_message_builds_rfc822():
    import base64
    import noesek.connectors.google as g

    captured = {}

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"id": "m1", "threadId": "t1"}

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResp()

    import httpx
    real = httpx.AsyncClient
    httpx.AsyncClient = FakeClient
    try:
        out = await g.send_message("tok", "sam@x.com", "tennis", "sat 3pm?")
    finally:
        httpx.AsyncClient = real

    assert out == {"id": "m1", "thread_id": "t1"}
    assert captured["url"].endswith("/messages/send")
    assert captured["headers"]["Authorization"] == "Bearer tok"
    raw = base64.urlsafe_b64decode(captured["json"]["raw"]).decode()
    assert raw.startswith("To: sam@x.com\r\nSubject: tennis\r\n")
    assert raw.endswith("sat 3pm?")

    with pytest.raises(ValueError):
        await g.send_message("tok", "not-an-email", "s", "b")
