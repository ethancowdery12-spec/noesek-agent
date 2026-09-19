import os

import pytest
from sqlalchemy import select, func
from noesek.config import settings
from noesek.db import Message, Session


@pytest.fixture(autouse=True)
def _authorize_test_senders(monkeypatch, tmp_path):
    # The WhatsApp ingress is gated by the vendored upstream authz chain; tests
    # authorize their senders through the WHATSAPP_ALLOWED_USERS projection.
    monkeypatch.setenv("WHATSAPP_ALLOWED_USERS", "15550001111,15550009999")
    yield

def payload(mid, text="hello", mtype="text", sender="15550001111"):
    msg = {"from": sender, "id": mid, "type": mtype}
    if mtype == "text": msg["text"] = {"body": text}
    return {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}

def test_verify_endpoint(db):
    from fastapi.testclient import TestClient
    from noesek.main import app
    with TestClient(app) as client:
        r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": settings.verify_token, "hub.challenge": "abc"})
        assert r.status_code == 200 and r.text == "abc"
        r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "abc"})
        assert r.status_code == 403

async def _count_external(mid):
    async with Session() as s:
        return (await s.execute(select(func.count()).select_from(Message).where(Message.external_id == mid))).scalar()

async def test_inbound_processed_and_deduped(db):
    from fastapi.testclient import TestClient
    from noesek.main import app
    with TestClient(app) as client:
        r = client.post("/webhooks/whatsapp", json=payload("wamid-dup-1"))
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert await _count_external("wamid-dup-1") == 1
        r = client.post("/webhooks/whatsapp", json=payload("wamid-dup-1"))
        assert r.status_code == 200
        assert await _count_external("wamid-dup-1") == 1

async def test_media_gets_acknowledgement_not_crash(db):
    from fastapi.testclient import TestClient
    from noesek.main import app
    with TestClient(app) as client:
        r = client.post("/webhooks/whatsapp", json=payload("wamid-img-1", mtype="image"))
        assert r.status_code == 200

async def test_rate_limit_blocks_flood(db):
    import noesek.channels.whatsapp as wa
    from fastapi.testclient import TestClient
    from noesek.main import app
    old = wa.limiter.limit; wa.limiter.limit = 2
    try:
        with TestClient(app) as client:
            for i in range(4):
                r = client.post("/webhooks/whatsapp", json=payload(f"wamid-flood-{i}", sender="15550009999"))
                assert r.status_code == 200
        async with Session() as s:
            n = (await s.execute(select(func.count()).select_from(Message).where(Message.external_id.like("wamid-flood-%")))).scalar()
        assert n == 2
    finally:
        wa.limiter.limit = old

async def test_healthz_and_metrics(db):
    from fastapi.testclient import TestClient
    from noesek.main import app
    with TestClient(app) as client:
        assert client.get("/healthz").json()["ok"] is True
        assert client.get("/readyz").status_code == 200
        assert client.get("/metrics").status_code == 200
