"""Slack/Telegram routers: signature verification, authz gate, controller routing."""
import hashlib
import hmac
import json
import time

import pytest

from noesek.config import settings

SLACK_SECRET = "slack-test-secret"


def slack_headers(body: bytes) -> dict:
    ts = str(int(time.time()))
    base = b"v0:" + ts.encode() + b":" + body
    sig = "v0=" + hmac.new(SLACK_SECRET.encode(), base, hashlib.sha256).hexdigest()
    return {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig}


@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "slack_signing_secret", SLACK_SECRET)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "tg-secret")
    monkeypatch.setenv("SLACK_ALLOWED_USERS", "U123")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "555")
    import noesek.channels.slack_router as sr
    import noesek.channels.telegram_router as tr
    monkeypatch.setattr(sr.transport, "signing_secret", SLACK_SECRET)
    monkeypatch.setattr(tr.transport, "webhook_secret", "tg-secret")
    return sr, tr


def test_slack_unsigned_request_rejected(db, configured):
    from fastapi.testclient import TestClient
    from noesek.main import app
    with TestClient(app) as c:
        assert c.post("/webhooks/slack", json={"type": "event_callback"}).status_code == 401


def test_slack_url_verification_challenge(db, configured):
    from fastapi.testclient import TestClient
    from noesek.main import app
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    with TestClient(app) as c:
        r = c.post("/webhooks/slack", content=body, headers=slack_headers(body))
        assert r.status_code == 200 and r.json() == {"challenge": "abc123"}


def test_slack_message_gated_then_handled(db, configured, monkeypatch):
    from fastapi.testclient import TestClient
    from noesek.main import app
    sent = []
    import noesek.channels.slack_router as sr
    async def fake_send(channel, text):
        sent.append((channel, text))
        return {"dry_run": True}
    monkeypatch.setattr(sr, "send_slack", fake_send)
    event = {"type": "event_callback", "event_id": "Ev1",
             "event": {"type": "message", "user": "U123", "channel": "C9", "text": "hi"}}
    body = json.dumps(event).encode()
    with TestClient(app) as c:
        r = c.post("/webhooks/slack", content=body, headers=slack_headers(body))
        assert r.status_code == 200
    assert sent and sent[0][0] == "C9"
    # Unauthorized sender is dropped before the controller.
    sent.clear()
    event["event"]["user"] = "U999"; event["event_id"] = "Ev2"
    body = json.dumps(event).encode()
    with TestClient(app) as c:
        c.post("/webhooks/slack", content=body, headers=slack_headers(body))
    assert sent == []


def test_telegram_secret_gate_and_flow(db, configured, monkeypatch):
    from fastapi.testclient import TestClient
    from noesek.main import app
    sent = []
    import noesek.channels.telegram_router as tr
    async def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return {"dry_run": True}
    monkeypatch.setattr(tr, "send_telegram", fake_send)
    update = {"update_id": 1, "message": {"message_id": 5, "from": {"id": 555},
                                          "chat": {"id": 777}, "text": "hi"}}
    with TestClient(app) as c:
        assert c.post("/webhooks/telegram", json=update).status_code == 401
        r = c.post("/webhooks/telegram", json=update,
                   headers={"X-Telegram-Bot-Api-Secret-Token": "tg-secret"})
        assert r.status_code == 200
    assert sent and sent[0][0] == "777"
