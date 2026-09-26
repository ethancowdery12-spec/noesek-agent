"""Obsidian channel: context folding, token store, pairing flow, message routing."""
import json
from types import SimpleNamespace

import pytest

from noesek.channels.authorization import NoesekAuthorizationGate
from noesek.channels.obsidian import (CONTEXT_CAP_CHARS, ContextTooLarge,
                                      ObsidianTokenStore, fold_context)


def test_fold_context_plain_text_passthrough():
    assert fold_context("hi", []) == ("hi", [])


def test_fold_context_file_and_folder_manifest():
    folded, manifest = fold_context("summarize", [
        {"path": "note.md", "content": "hello world"},
        {"path": "projects/", "paths": ["projects/a.md", "projects/b.md"]},
    ])
    assert "note.md (11 chars)" in manifest[0]
    assert "projects/ (2 paths listed)" in manifest[1]
    assert "[obsidian context: 2 attachment(s):" in folded
    assert "# note.md\nhello world" in folded
    assert folded.endswith("summarize")


def test_fold_context_selection_appended():
    folded, _ = fold_context("fix this", [{"path": "n.md", "content": "body", "selection": "line 2"}])
    assert "## selection\nline 2" in folded


def test_fold_context_over_cap_rejected():
    with pytest.raises(ContextTooLarge):
        fold_context("x", [{"path": "big.md", "content": "y" * (CONTEXT_CAP_CHARS + 1)}])


def test_token_store_roundtrip_and_revoke(tmp_path):
    store = ObsidianTokenStore(home=tmp_path)
    token = store.issue("dev-1")
    assert store.validate(token) == "dev-1"
    assert store.validate("bogus") is None
    assert store.validate("") is None
    # tokens are hashed at rest
    assert token not in store.path.read_text()
    assert store.revoke_device("dev-1") == 1
    assert store.validate(token) is None


@pytest.fixture
def gate(tmp_path):
    return NoesekAuthorizationGate(home=tmp_path)


@pytest.fixture
def client(db, gate, tmp_path, monkeypatch):
    import noesek.channels.obsidian_router as obsr
    monkeypatch.setattr(obsr, "get_gate", lambda: gate)
    monkeypatch.setattr(obsr, "store", ObsidianTokenStore(home=tmp_path / "tok"))
    replies = []

    async def fake_handle(cid, text, external_id=None):
        replies.append((cid, text))
        return SimpleNamespace(text=f"echo:{text.splitlines()[-1]}")

    monkeypatch.setattr(obsr, "get_controller", lambda: SimpleNamespace(handle=fake_handle))
    from fastapi.testclient import TestClient
    from noesek.main import app
    with TestClient(app) as c:
        c.replies = replies
        yield c


def _pair_device(c, gate, device="dev-1"):
    r = c.post("/channels/obsidian/pair/start", json={"device_id": device, "device_name": "vault"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    code = r.json()["code"]
    assert c.get("/channels/obsidian/pair/status", params={"device_id": device}).json()["status"] == "pending"
    assert gate.approve_code("obsidian", code)
    r = c.get("/channels/obsidian/pair/status", params={"device_id": device})
    assert r.json()["status"] == "approved"
    return r.json()["token"]


def test_pairing_flow_issues_token_after_approval(db, gate, client):
    token = _pair_device(client, gate)
    assert token and len(token) > 20


def test_message_requires_token(db, gate, client):
    assert client.post("/channels/obsidian/messages", json={"text": "hi"}).status_code == 401
    r = client.post("/channels/obsidian/messages", json={"text": "hi"},
                    headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_message_routes_to_controller_with_context(db, gate, client):
    token = _pair_device(client, gate)
    r = client.post("/channels/obsidian/messages",
                    json={"text": "what is this", "client_msg_id": "m1",
                          "context": [{"path": "note.md", "content": "vault body"}]},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "echo:what is this"
    assert body["attachments_sent"] == ["note.md (10 chars)"]
    sent_text = client.replies[-1][1]
    assert "[obsidian context:" in sent_text and "vault body" in sent_text


def test_revoked_device_rejected(db, gate, client):
    token = _pair_device(client, gate)
    assert gate.revoke("obsidian", "dev-1")
    r = client.post("/channels/obsidian/messages", json={"text": "hi"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_context_cap_returns_413(db, gate, client):
    token = _pair_device(client, gate)
    r = client.post("/channels/obsidian/messages",
                    json={"text": "hi", "context": [{"path": "b.md", "content": "z" * (CONTEXT_CAP_CHARS + 1)}]},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 413


def test_already_paired_device_rekeys_without_code(db, gate, client):
    token1 = _pair_device(client, gate)
    r = client.post("/channels/obsidian/pair/start", json={"device_id": "dev-1"})
    assert r.json()["status"] == "approved"
    token2 = r.json()["token"]
    assert token2 != token1
