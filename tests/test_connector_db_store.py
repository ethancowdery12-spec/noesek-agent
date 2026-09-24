"""DbTokenStore (wearable-OAuth tranche PR1): grants/states survive in Postgres,
not the ephemeral host filesystem that wiped them on every redeploy."""
import time

import pytest

from noesek.connectors import DbTokenStore


@pytest.mark.asyncio
async def test_grant_roundtrip_and_overwrite(db):
    store = DbTokenStore()
    await store.put("google", "chat-1", "tok-a", ("gmail.readonly",))
    grant = await store.get("google", "chat-1")
    assert grant["access_token"] == "tok-a" and grant["scopes"] == ["gmail.readonly"]
    assert isinstance(grant["obtained_at"], int)
    await store.put("google", "chat-1", "tok-b", ("gmail.readonly", "gmail.send"))
    grant = await store.get("google", "chat-1")
    assert grant["access_token"] == "tok-b" and len(grant["scopes"]) == 2


@pytest.mark.asyncio
async def test_grants_isolated_by_connector_and_chat(db):
    store = DbTokenStore()
    await store.put("google", "chat-1", "tok-g")
    await store.put("github", "chat-1", "tok-gh")
    assert (await store.get("google", "chat-1"))["access_token"] == "tok-g"
    assert (await store.get("github", "chat-1"))["access_token"] == "tok-gh"
    assert await store.get("google", "chat-2") is None
    assert await store.connected_chats("google") == ["chat-1"]
    assert await store.connected_chats("strava") == []


@pytest.mark.asyncio
async def test_state_pop_and_expiry(db, monkeypatch):
    store = DbTokenStore()
    await store.put_state("st-1", "google", "chat-1", "https://x/cb")
    entry = await store.pop_state("st-1")
    assert entry["connector"] == "google" and entry["chat_id"] == "chat-1"
    assert entry["redirect_uri"] == "https://x/cb"
    assert await store.pop_state("st-1") is None  # one-shot

    await store.put_state("st-2", "google", "chat-1")
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 7200)
    assert await store.pop_state("st-2") is None  # expired


@pytest.mark.asyncio
async def test_default_store_is_db_backed(db):
    from noesek.connectors import default_store
    assert isinstance(default_store(), DbTokenStore)
