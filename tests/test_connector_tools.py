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
