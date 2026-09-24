"""fitness_query tool + strava connector (wearable-OAuth tranche PR2)."""
import pytest
from sqlalchemy import select

from noesek import connectors
from noesek.connectors import strava as st
from noesek.db import Conversation, Memory, Session
from noesek.tools.fitness_query import FitnessQueryInput, fitness_query_handler

# the mapped shape strava.list_activities returns
ACTS = [
    {"id": 901, "name": "Morning Run", "sport": "Run", "start_date": "2026-09-23T07:30:00Z",
     "distance_km": 5.0, "moving_time_min": 25.5, "elevation_m": 42.0,
     "avg_hr": 148.0, "max_hr": 171.0},
    {"id": 902, "name": "Evening Ride", "sport": "Ride", "start_date": "2026-09-22T18:05:00Z",
     "distance_km": 20.0, "moving_time_min": 50.0, "elevation_m": 150.0,
     "avg_hr": None, "max_hr": None},
]


@pytest.fixture()
async def chat(db):
    async with Session() as s:
        conv = Conversation(channel="local", external_user_id="ethan-main")
        s.add(conv)
        await s.commit()
        return conv.id


async def _fake_list(token, limit=10, after_ts=0):
    return ACTS


@pytest.mark.asyncio
async def test_strava_connector_registered():
    c = connectors.get("strava")
    assert c is not None and c.scope_sep == ","
    url, state = connectors.build_authorize_url(c, "chat-1", "https://x/cb")
    assert "scope=read%2Cactivity%3Aread_all" in url or "scope=read,activity" in url.replace("%2C", ",")


@pytest.mark.asyncio
async def test_not_connected_errors_cleanly(chat):
    out = await fitness_query_handler(chat)(FitnessQueryInput())
    assert out["ok"] is False and "not connected" in out["error"]


@pytest.mark.asyncio
async def test_reads_and_logs_deduped(chat, monkeypatch):
    monkeypatch.setattr(st, "list_activities", _fake_list)
    await connectors.default_store().put("strava", "ethan-main", "tok-s", ("read",))
    out = await fitness_query_handler(chat)(FitnessQueryInput(days=7))
    assert out["ok"] and out["count"] == 2
    r = out["activities"][0]
    assert r["activity"] == "Run" and r["distance_km"] == 5.0 and r["avg_hr"] == 148.0
    assert "not medical advice" in out["note"]
    async with Session() as s:
        n = len((await s.execute(select(Memory).where(Memory.kind == "workout"))).scalars().all())
    assert n == 0  # read-only by default

    out = await fitness_query_handler(chat)(FitnessQueryInput(days=7, log=True))
    assert out["logged"] == 2 and out["skipped_duplicates"] == 0
    out = await fitness_query_handler(chat)(FitnessQueryInput(days=7, log=True))
    assert out["logged"] == 0 and out["skipped_duplicates"] == 2


@pytest.mark.asyncio
async def test_expired_grant_refreshes_once(chat, monkeypatch):
    calls = {"n": 0}
    async def flaky(token, limit=10, after_ts=0):
        calls["n"] += 1
        if token == "old-tok":
            raise st.GrantMissing("expired")
        return ACTS
    monkeypatch.setattr(st, "list_activities", flaky)
    async def fake_refresh(connector, chat_id):
        assert connector == "strava" and chat_id == "ethan-main"
        return "new-tok"
    monkeypatch.setattr(connectors, "refresh_grant", fake_refresh)
    await connectors.default_store().put("strava", "ethan-main", "old-tok", ("read",))
    out = await fitness_query_handler(chat)(FitnessQueryInput())
    assert out["ok"] and out["count"] == 2

    async def no_refresh(connector, chat_id):
        return None
    monkeypatch.setattr(connectors, "refresh_grant", no_refresh)
    await connectors.default_store().put("strava", "ethan-main", "old-tok", ("read",))
    out = await fitness_query_handler(chat)(FitnessQueryInput())
    assert out["ok"] is False and "reconnect" in out["error"]
