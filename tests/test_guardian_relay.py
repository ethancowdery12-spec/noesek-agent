"""Guardian Kaggle-relay (docs/GUARDIAN_SERVING.md): the job store, the keyed
relay endpoints, and the remote-scorer path. No model, no network - the relay
itself is simulated by completing jobs directly in the store."""
import json
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noesek.config import settings
from noesek.guardian import gate as gg
from noesek.guardian import scorer as sc
from noesek.guardian.relay_router import router
from noesek.guardian.relay_store import JobStore, _reset_for_tests, get_store


@pytest.fixture
def store(tmp_path):
    s = JobStore(str(tmp_path / "jobs.db"))
    yield s


def test_store_roundtrip(store):
    jid = store.enqueue("tool: {}\nreasoning: r\ncontext: c")
    job = store.claim_next()
    assert job["id"] == jid and job["status"] == "claimed"
    assert store.claim_next() is None  # already claimed, nothing else pending
    assert store.complete(jid, {"deny_score": 0.9, "esc_prob": 0.1, "top_risk": "destructive"})
    row = store.get(jid)
    assert row["status"] == "done"
    assert json.loads(row["result"])["deny_score"] == 0.9
    assert not store.complete(jid, {"deny_score": 0.1})  # second completion rejected


def test_store_skips_expired(store):
    jid = store.enqueue("state", ttl=-1.0)  # already expired
    assert store.claim_next() is None
    assert store.get(jid)["status"] == "pending"  # still visible, just not claimable
    live = store.enqueue("state2")
    assert store.claim_next()["id"] == live


def test_store_counts_and_sweep(store):
    store.enqueue("a")
    b = store.enqueue("b")
    done_id = store.claim_next()["id"]  # oldest first = a
    store.complete(done_id, {"deny_score": 0.0, "esc_prob": 0.0})
    counts = store.counts()
    assert counts.get("done") == 1 and counts["live_open"] >= 0
    store.sweep()
    assert store.get(done_id) is None  # done jobs swept
    assert store.get(b) is not None    # live pending job survives


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "guardian_relay_key", "test-key")
    _reset_for_tests()
    monkeypatch.setattr(settings, "guardian_relay_db", str(tmp_path / "relay.db"))
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    yield c
    _reset_for_tests()


KEY = {"X-Guardian-Relay-Key": "test-key"}


def test_endpoints_require_key(client):
    assert client.get("/internal/guardian/jobs/next", params={"wait": 0}).status_code == 403
    assert client.post("/internal/guardian/jobs/x/result",
                       json={"deny_score": 0.1, "esc_prob": 0.0}).status_code == 403
    r = client.get("/internal/guardian/jobs/next", params={"wait": 0},
                   headers={"X-Guardian-Relay-Key": "wrong"})
    assert r.status_code == 403


def test_endpoints_503_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "guardian_relay_key", "")
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    assert c.get("/internal/guardian/health").status_code == 503


def test_next_result_flow(client):
    store = get_store()
    jid = store.enqueue("tool: {}\nreasoning: r\ncontext: c")
    r = client.get("/internal/guardian/jobs/next", params={"wait": 1}, headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == jid and body["state"].startswith("tool:")
    r = client.post(f"/internal/guardian/jobs/{jid}/result",
                    json={"deny_score": 0.97, "esc_prob": 0.02, "top_risk": "destructive"},
                    headers=KEY)
    assert r.status_code == 200
    row = store.get(jid)
    assert row["status"] == "done"
    r = client.post(f"/internal/guardian/jobs/{jid}/result",
                    json={"deny_score": 0.1, "esc_prob": 0.0}, headers=KEY)
    assert r.status_code == 404  # already completed
    r = client.get("/internal/guardian/health", headers=KEY)
    assert r.status_code == 200 and r.json()["ok"]


def test_next_empty_returns_204(client):
    r = client.get("/internal/guardian/jobs/next", params={"wait": 0}, headers=KEY)
    assert r.status_code == 204


def test_remote_scorer_roundtrip(tmp_path, monkeypatch):
    _reset_for_tests()
    monkeypatch.setattr(settings, "guardian_relay_db", str(tmp_path / "relay.db"))
    store = get_store()

    def fake_relay():
        time.sleep(0.2)
        job = store.claim_next()
        assert job is not None
        store.complete(job["id"], {"deny_score": 0.88, "esc_prob": 0.05, "top_risk": "exfiltration"})

    t = threading.Thread(target=fake_relay)
    t.start()
    out = sc.score_state_via_relay("tool: {}\nreasoning: r\ncontext: c", 5.0)
    t.join()
    assert out == {"deny_score": 0.88, "esc_prob": 0.05, "top_risk": "exfiltration"}
    _reset_for_tests()


def test_remote_scorer_times_out(tmp_path, monkeypatch):
    _reset_for_tests()
    monkeypatch.setattr(settings, "guardian_relay_db", str(tmp_path / "relay.db"))
    with pytest.raises(TimeoutError):
        sc.score_state_via_relay("state", 1.0)
    _reset_for_tests()


@pytest.mark.asyncio
async def test_gate_uses_relay_when_remote(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_remote", True)
    monkeypatch.setattr(settings, "guardian_score_timeout_seconds", 3.0)
    _reset_for_tests()
    monkeypatch.setattr(settings, "guardian_relay_db", str(tmp_path / "relay.db"))

    def fake_relay():
        time.sleep(0.2)
        job = get_store().claim_next()
        get_store().complete(job["id"],
                             {"deny_score": 0.99, "esc_prob": 0.0, "top_risk": "destructive"})

    t = threading.Thread(target=fake_relay)
    t.start()
    v = await gg.gate_tool_call("run_python", {"code": "rm -rf /"}, "cleanup", "test")
    t.join()
    assert v is not None and v.verdict == "deny" and v.deny_score == 0.99
    _reset_for_tests()


@pytest.mark.asyncio
async def test_gate_remote_timeout_fail_open(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "guardian_enabled", True)
    monkeypatch.setattr(settings, "guardian_remote", True)
    monkeypatch.setattr(settings, "guardian_fail_mode", "open")
    monkeypatch.setattr(settings, "guardian_score_timeout_seconds", 1.5)
    _reset_for_tests()
    monkeypatch.setattr(settings, "guardian_relay_db", str(tmp_path / "relay.db"))
    v = await gg.gate_tool_call("run_python", {"code": "print(1)"}, "r", "test")
    assert v is None  # no relay answering -> fail open, controller proceeds
    _reset_for_tests()


def test_canary_roundtrip(client):
    from noesek.guardian import relay_router as rr
    rr._canary_last = 0.0

    def complete():
        time.sleep(0.5)
        job = get_store().claim_next()
        assert job is not None and job["state"].startswith("read_file:")
        get_store().complete(
            job["id"], {"deny_score": 0.01, "esc_prob": 0.0, "top_risk": "read_only"})

    t = threading.Thread(target=complete)
    t.start()
    r = client.post("/internal/guardian/canary", params={"timeout": 5})
    t.join()
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["verdict"]["top_risk"] == "read_only"
    assert body["latency_ms"] >= 0


def test_canary_timeout(client):
    from noesek.guardian import relay_router as rr
    rr._canary_last = 0.0
    r = client.post("/internal/guardian/canary", params={"timeout": 1})
    assert r.status_code == 504


def test_canary_rate_limited(client):
    from noesek.guardian import relay_router as rr
    rr._canary_last = 0.0
    client.post("/internal/guardian/canary", params={"timeout": 1})
    r = client.post("/internal/guardian/canary", params={"timeout": 1})
    assert r.status_code == 429
