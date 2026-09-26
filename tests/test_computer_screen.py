"""Offline gates for the computer screen: control lease, RFB input filter, display
tickets and endpoint fencing. No X server, no browser, no network."""
from __future__ import annotations

import json
import os
import time

import pytest

from src.noesek.computer import screen_lease, screen_runtime
from src.noesek.computer.rfb_filter import RfbClientFilter


@pytest.fixture(autouse=True)
def screen_home(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_COMPUTER_HOME", str(tmp_path))
    yield tmp_path


# ---- lease ----

def test_lease_defaults_to_agent():
    lease = screen_lease.get()
    assert lease.holder == screen_lease.AGENT
    assert not screen_lease.human_holds()


def test_takeover_and_handback_roundtrip():
    lease = screen_lease.acquire("v1", reason="login needed")
    assert lease.holder == screen_lease.HUMAN and lease.viewer_id == "v1"
    assert lease.reason == "login needed" and lease.epoch == 1
    assert screen_lease.human_holds()
    assert screen_lease.viewer_may_send_input("v1")
    assert not screen_lease.viewer_may_send_input("v2")
    lease = screen_lease.release("v1")
    assert lease.holder == screen_lease.AGENT and lease.epoch == 2
    assert not screen_lease.human_holds()


def test_second_viewer_evicts_first():
    screen_lease.acquire("v1")
    lease = screen_lease.acquire("v2")
    assert lease.viewer_id == "v2"
    assert not screen_lease.viewer_may_send_input("v1")
    # Stale viewer's release must not yank the new holder's control.
    lease = screen_lease.release("v1")
    assert lease.holder == screen_lease.HUMAN and lease.viewer_id == "v2"


def test_same_viewer_reacquire_is_noop():
    screen_lease.acquire("v1", reason="first")
    lease = screen_lease.acquire("v1", reason="second")
    assert lease.epoch == 1 and lease.reason == "first"


def test_release_when_agent_holds_is_noop():
    lease = screen_lease.release()
    assert lease.holder == screen_lease.AGENT and lease.epoch == 0


def test_unless_human_blocks_bare_release():
    screen_lease.acquire("v1")
    lease = screen_lease.release(unless_human=True)
    assert lease.holder == screen_lease.HUMAN


def test_corrupt_lease_file_fails_closed():
    path = screen_lease._path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    lease = screen_lease.get()
    assert lease.holder == screen_lease.HUMAN  # never let the agent act on a human's screen


def test_public_view_hides_viewer_id():
    screen_lease.acquire("secret-viewer-id")
    view = screen_lease.public_view(screen_lease.get())
    assert view["viewer_id"] is None
    assert view["viewer_hash"] and view["viewer_hash"] != "secret-viewer-id"


def test_lease_file_is_private():
    screen_lease.acquire("v1")
    path = screen_lease._path()
    assert (path.stat().st_mode & 0o777) == 0o600


# ---- RFB filter ----

def _handshake() -> bytes:
    return b"RFB 003.008\n" + b"\x01" + b"\x00"  # version + security choice + ClientInit(shared=0)


def test_handshake_passthrough_forces_shared():
    f = RfbClientFilter(lambda: False)
    out = f.feed(_handshake())
    assert out == b"RFB 003.008\n" + b"\x01" + b"\x01"  # shared flag forced on


def test_watcher_gets_noninput_only():
    f = RfbClientFilter(lambda: False)
    f.feed(_handshake())
    update_req = bytes([3, 0, 0, 0, 0, 0, 10, 0, 10, 0])  # FramebufferUpdateRequest
    key = bytes([4, 0, 0, 0, 0, 0, 0, 0x61])  # KeyEvent 'a'
    pointer = bytes([5, 1, 0, 10, 0, 10])
    out = f.feed(update_req + key + pointer)
    assert out == update_req  # input dropped, non-input forwarded


def test_holder_input_passes_and_gate_flips_midstream():
    allow = {"ok": True}
    f = RfbClientFilter(lambda: allow["ok"])
    f.feed(_handshake())
    key = bytes([4, 0, 0, 0, 0, 0, 0, 0x61])
    assert f.feed(key) == key
    allow["ok"] = False
    assert f.feed(key) == b""  # the very next key event is gated


def test_clipboard_over_cap_rejected():
    f = RfbClientFilter(lambda: True)
    f.feed(_handshake())
    big = bytes([6, 0, 0, 0]) + (300 * 1024).to_bytes(4, "big")
    with pytest.raises(ValueError):
        f.feed(big)


def test_unknown_message_type_drops_stream():
    f = RfbClientFilter(lambda: True)
    f.feed(_handshake())
    with pytest.raises(ValueError):
        f.feed(bytes([99, 0, 0, 0]))


def test_partial_message_buffers():
    f = RfbClientFilter(lambda: True)
    f.feed(_handshake()[:6])
    f.feed(_handshake()[6:])
    key = bytes([4, 0, 0, 0, 0, 0, 0, 0x61])
    assert f.feed(key[:3]) == b""
    assert f.feed(key[3:]) == key


# ---- runtime status (no Xvnc in the sandbox) ----

def test_runtime_status_shape():
    st = screen_runtime.status()
    assert set(st) >= {"installed", "running", "geometry", "control", "free_memory_mb"}
    assert st["running"] is False
    assert st["control"]["holder"] == "agent"


def test_stop_without_force_refused_while_human_holds():
    screen_lease.acquire("v1")
    with pytest.raises(RuntimeError):
        screen_runtime.stop()
    screen_runtime.stop(force=True)
    assert not screen_lease.human_holds()


# ---- endpoints ----

@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_COMPUTER_HOME", str(tmp_path))
    monkeypatch.setenv("NOESEK_SCREEN_TOKEN", "t0ken")
    from fastapi.testclient import TestClient
    from src.noesek.computer.server import app
    return TestClient(app)


def test_endpoints_require_configured_token(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_COMPUTER_HOME", str(tmp_path))
    monkeypatch.delenv("NOESEK_SCREEN_TOKEN", raising=False)
    from fastapi.testclient import TestClient
    from src.noesek.computer.server import app
    c = TestClient(app)
    assert c.get("/computer/screen").status_code == 503


def test_bad_token_rejected(client):
    assert client.get("/computer/screen").status_code == 403
    assert client.get("/computer/screen", headers={"Authorization": "Bearer wrong"}).status_code == 403


def test_status_with_token(client):
    r = client.get("/computer/screen", headers={"Authorization": "Bearer t0ken"})
    assert r.status_code == 200
    assert r.json()["control"]["holder"] == "agent"


def test_takeover_fences_screenshot_and_input(client):
    r = client.post("/computer/screen/takeover", headers={"Authorization": "Bearer t0ken"})
    assert r.status_code == 200
    viewer_id = r.json()["viewer_id"]
    # Agent-side tools now refuse before touching the display at all.
    assert client.get("/computer/screenshot").status_code == 409
    assert client.post("/computer/input", json={"action": "move", "x": 1, "y": 1}).status_code == 409
    r = client.post("/computer/screen/handback", params={"viewer_id": viewer_id},
                    headers={"Authorization": "Bearer t0ken"})
    assert r.json()["control"]["holder"] == "agent"


def test_ticket_single_use_and_expiry(client, monkeypatch):
    monkeypatch.setattr(screen_runtime, "running", lambda: True)
    r = client.post("/computer/screen/ticket", headers={"Authorization": "Bearer t0ken"})
    assert r.status_code == 200
    ticket = r.json()["ticket"]
    from src.noesek.computer import screen_bridge
    info = screen_bridge._consume_ticket(ticket)
    assert info is not None
    assert screen_bridge._consume_ticket(ticket) is None  # second use is a different socket's 4401
    r = client.post("/computer/screen/ticket", headers={"Authorization": "Bearer t0ken"})
    t2 = r.json()["ticket"]
    screen_bridge._tickets[t2]["expires"] = time.time() - 1
    assert screen_bridge._consume_ticket(t2) is None
