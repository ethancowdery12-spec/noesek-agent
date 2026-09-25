"""DbProactiveStore: proactive activations survive in Postgres, not the
ephemeral host filesystem that wiped them on every redeploy."""
import time

import pytest

from noesek.proactive import DbProactiveStore


@pytest.mark.asyncio
async def test_activate_get_all_roundtrip(db):
    store = DbProactiveStore()
    entry = await store.activate("chat-1", goal="water the plants", interval_seconds=120)
    assert entry["active"] is True and entry["interval_seconds"] == 120
    assert entry["next_tick_at"] <= int(time.time())  # first tick immediately
    got = await store.get("chat-1")
    assert got["goal"] == "water the plants" and got["active"] is True
    everything = await store.all()
    assert set(everything) == {"chat-1"}
    assert await store.get("chat-2") is None


@pytest.mark.asyncio
async def test_activate_clamps_interval_and_overwrites(db):
    store = DbProactiveStore()
    entry = await store.activate("chat-1", interval_seconds=5)
    assert entry["interval_seconds"] == 60  # clamped to the 60s floor
    await store.activate("chat-1", goal="new goal", interval_seconds=600)
    got = await store.get("chat-1")
    assert got["goal"] == "new goal" and got["interval_seconds"] == 600


@pytest.mark.asyncio
async def test_pause_excludes_from_due(db):
    store = DbProactiveStore()
    await store.activate("chat-1")
    await store.activate("chat-2")
    assert await store.due_chats() == ["chat-1", "chat-2"]
    assert await store.pause("chat-1") is True
    assert await store.due_chats() == ["chat-2"]
    assert (await store.get("chat-1"))["active"] is False
    assert await store.pause("nobody") is False


@pytest.mark.asyncio
async def test_reschedule_pushes_next_tick_out(db):
    store = DbProactiveStore()
    await store.activate("chat-1", interval_seconds=3600)
    assert await store.due_chats() == ["chat-1"]  # due immediately after activate
    await store.reschedule("chat-1")
    assert await store.due_chats() == []  # pushed ~1h out
    got = await store.get("chat-1")
    assert got["next_tick_at"] > int(time.time()) + 3500
    await store.reschedule("nobody")  # no-op, no crash
