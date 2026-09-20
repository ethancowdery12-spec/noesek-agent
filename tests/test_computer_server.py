"""Computer runtime: local chat channel maps chat_id -> session -> reply.

Hermetic: stubs at the server-module attribute level. No env changes,
no module reloads, no real database.
"""
from __future__ import annotations

import types

import pytest
from httpx import ASGITransport, AsyncClient

from noesek.computer import server


def _stub_session(conversations):
    class FakeConv:
        def __init__(self, cid):
            self.id = cid

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            pass

    async def fake_get_or_create(session, channel, external_id):
        key = (channel, external_id)
        if key not in conversations:
            conversations[key] = FakeConv(len(conversations) + 1)
        return conversations[key]

    return FakeSession, fake_get_or_create


@pytest.mark.asyncio
async def test_chat_creates_session_and_replies(monkeypatch):
    conversations = {}
    FakeSession, fake_get_or_create = _stub_session(conversations)
    monkeypatch.setattr(server, "Session", FakeSession)
    monkeypatch.setattr(server, "get_or_create_conversation", fake_get_or_create)

    seen = {}

    class FakeResult:
        text = "hello back"

    async def fake_handle(cid, text, external_id=None):
        seen["cid"] = cid
        seen["text"] = text
        return FakeResult()

    monkeypatch.setattr(server, "get_controller", lambda: types.SimpleNamespace(handle=fake_handle))

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r1 = await c.post("/chat", json={"chat_id": "ethan-1", "text": "hi"})
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["reply"] == "hello back"
        assert body["chat_id"] == "ethan-1"
        r2 = await c.post("/chat", json={"chat_id": "ethan-1", "text": "again"})
        assert r2.json()["conversation_id"] == body["conversation_id"]
        r3 = await c.post("/chat", json={"chat_id": "ethan-2", "text": "hi"})
        assert r3.json()["conversation_id"] != body["conversation_id"]
        assert seen["text"] == "hi"


@pytest.mark.asyncio
async def test_chat_requires_fields(monkeypatch):
    conversations = {}
    FakeSession, fake_get_or_create = _stub_session(conversations)
    monkeypatch.setattr(server, "Session", FakeSession)
    monkeypatch.setattr(server, "get_or_create_conversation", fake_get_or_create)
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        assert (await c.post("/chat", json={"chat_id": "", "text": "hi"})).status_code == 400
        assert (await c.post("/chat", json={"chat_id": "x", "text": "  "})).status_code == 400


@pytest.mark.asyncio
async def test_screenshot_503_without_display(monkeypatch):
    monkeypatch.delitem(__import__("os").environ, "DISPLAY", raising=False)
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r = await c.get("/computer/screenshot")
        assert r.status_code == 503


@pytest.mark.asyncio
async def test_healthz():
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r = await c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True


class _FakeExecutor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def run(self, plan):
        return {
            "origin": plan.origin,
            "digest": plan.digest,
            "steps": [
                {"step": 0, "type": "navigate", "url": plan.actions[0].get("url"), "title": "T"},
                {"step": 1, "type": "extract_text", "selector": "body", "text": "x" * 9000},
                {"step": 2, "type": "screenshot", "png_base64": "aGVsbG8="},
            ],
        }


@pytest.mark.asyncio
async def test_browse_builds_validated_plan_and_truncates(monkeypatch):
    monkeypatch.setattr(server, "PlaywrightExecutor", _FakeExecutor)
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r = await c.post("/computer/browse", json={"url": "https://example.com/"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["origin"] == "https://example.com"
    assert data["steps"][0]["title"] == "T"
    assert len(data["steps"][1]["text"]) == 8000
    assert data["steps"][1]["text_truncated"] is True
    assert data["steps"][2]["png_base64"] == "aGVsbG8="


@pytest.mark.asyncio
async def test_browse_rejects_bad_url_and_disallowed_origin(monkeypatch):
    monkeypatch.setattr(server, "PlaywrightExecutor", _FakeExecutor)
    monkeypatch.setattr(server.settings, "computer_allowed_origins", "https://allowed.example")
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        bad = await c.post("/computer/browse", json={"url": "ftp://x"})
        assert bad.status_code == 400
        blocked = await c.post("/computer/browse", json={"url": "https://evil.example/"})
        assert blocked.status_code == 403
        ok = await c.post("/computer/browse", json={"url": "https://allowed.example/page"})
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_connectors_list_and_token_flow(monkeypatch, tmp_path):
    from noesek import connectors

    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    monkeypatch.setenv("NOESEK_CONNECTOR_GITHUB_CLIENT_ID", "cid-123")

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        r = await c.get("/connectors", params={"chat_id": "ethan-main"})
        assert r.status_code == 200
        by_name = {x["name"]: x for x in r.json()["connectors"]}
        assert set(by_name) == {"github", "google"}
        assert by_name["github"]["configured"] is True
        assert by_name["google"]["configured"] is False
        assert by_name["github"]["connected"] is False

        noauth = await c.post("/connectors/google/auth-start", json={"chat_id": "ethan-main"})
        assert noauth.status_code == 400  # no client id configured

        start = await c.post("/connectors/github/auth-start", json={"chat_id": "ethan-main"})
        assert start.status_code == 200
        url = start.json()["authorize_url"]
        assert url.startswith("https://github.com/login/oauth/authorize?")
        assert "client_id=cid-123" in url and "state=ethan-main%3A" in url

        dep = await c.post("/connectors/github/token",
                           json={"chat_id": "ethan-main", "access_token": "tok-1"})
        assert dep.status_code == 200

        r2 = await c.get("/connectors", params={"chat_id": "ethan-main"})
        assert {x["name"]: x for x in r2.json()["connectors"]}["github"]["connected"] is True
        # token file is private and chat-scoped
        assert oct((tmp_path / "connectors.json").stat().st_mode)[-3:] == "600"
        assert store.get("github", "ethan-main")["access_token"] == "tok-1"
        assert store.get("github", "someone-else") is None

        unknown = await c.post("/connectors/nope/token",
                               json={"chat_id": "x", "access_token": "y"})
        assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_oauth_callback_completes_flow(monkeypatch, tmp_path):
    from noesek import connectors

    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    monkeypatch.setenv("NOESEK_CONNECTOR_GITHUB_CLIENT_ID", "cid-123")
    monkeypatch.setenv("NOESEK_CONNECTOR_GITHUB_CLIENT_SECRET", "sec-xyz")

    seen = {}

    async def fake_exchange(connector, code, redirect_uri):
        seen["code"] = code
        seen["redirect_uri"] = redirect_uri
        return "tok-live"

    monkeypatch.setattr(connectors, "exchange_code", fake_exchange)

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        start = await c.post("/connectors/github/auth-start",
                             json={"chat_id": "ethan-main",
                                   "redirect_uri": "http://127.0.0.1:8780/connectors/callback"})
        state = start.json()["state"]

        bad = await c.get("/connectors/callback", params={"code": "abc", "state": "bogus"})
        assert bad.status_code == 400

        cb = await c.get("/connectors/callback", params={"code": "abc", "state": state})
        assert cb.status_code == 200
        assert "Connected github" in cb.text
        assert seen == {"code": "abc", "redirect_uri": "http://127.0.0.1:8780/connectors/callback"}
        assert store.get("github", "ethan-main")["access_token"] == "tok-live"

        # state is single-use
        replay = await c.get("/connectors/callback", params={"code": "abc", "state": state})
        assert replay.status_code == 400


@pytest.mark.asyncio
async def test_proactive_flow_and_idle_withholding(monkeypatch, tmp_path):
    from noesek import proactive

    store = proactive.ProactiveStore(tmp_path / "proactive.json")
    monkeypatch.setattr(proactive, "default_store", lambda: store)

    conversations = {}
    FakeSession, fake_get_or_create = _stub_session(conversations)
    monkeypatch.setattr(server, "Session", FakeSession)
    monkeypatch.setattr(server, "get_or_create_conversation", fake_get_or_create)

    replies = iter(["IDLE", "ordered the thing"])
    seen_texts = []

    async def fake_handle(cid, text, external_id=None):
        seen_texts.append(text)
        return types.SimpleNamespace(text=next(replies))

    monkeypatch.setattr(server, "get_controller", lambda: types.SimpleNamespace(handle=fake_handle))

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        act = await c.post("/proactive/activate",
                           json={"chat_id": "ethan-main", "goal": "watch the build", "interval_seconds": 60})
        assert act.status_code == 200
        assert act.json()["active"] is True and act.json()["interval_seconds"] == 60
        assert oct((tmp_path / "proactive.json").stat().st_mode)[-3:] == "600"

        # due immediately after activate
        assert store.due_chats() == ["ethan-main"]

        # first tick: controller goes IDLE -> withheld, not acted
        t1 = await c.post("/proactive/tick", json={"chat_id": "ethan-main"})
        assert t1.status_code == 200
        assert t1.json() == {"chat_id": "ethan-main", "acted": False, "reply": ""}
        assert "watch the build" in seen_texts[0]

        # second tick: controller acts -> reply surfaces
        t2 = await c.post("/proactive/tick", json={"chat_id": "ethan-main"})
        assert t2.json()["acted"] is True and t2.json()["reply"] == "ordered the thing"

        # rescheduled into the future after each tick
        assert store.due_chats() == []

        pause = await c.post("/proactive/pause", json={"chat_id": "ethan-main"})
        assert pause.status_code == 200
        paused_tick = await c.post("/proactive/tick", json={"chat_id": "ethan-main"})
        assert paused_tick.status_code == 404

        listing = await c.get("/proactive")
        assert listing.json()["chats"]["ethan-main"]["active"] is False


@pytest.mark.asyncio
async def test_gmail_tool_reads_with_stored_grant(monkeypatch, tmp_path):
    from noesek import connectors
    from noesek.connectors import google as gtool

    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    store.put("google", "ethan-main", "tok-g", ("gmail.readonly",))

    seen = {}

    async def fake_list(token, max_results):
        seen["token"] = token
        seen["max"] = max_results
        return [{"id": "m1", "from": "sam@x.com", "subject": "tennis?",
                 "date": "Sun, 20 Sep 2026 09:00:00 -0500", "snippet": "sat 3pm?"}]

    monkeypatch.setattr(gtool, "list_messages", fake_list)

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        no_grant = await c.get("/connectors/google/gmail/messages", params={"chat_id": "nobody"})
        assert no_grant.status_code == 403
        r = await c.get("/connectors/google/gmail/messages",
                        params={"chat_id": "ethan-main", "max_results": 3})
        assert r.status_code == 200
        assert r.json()["messages"][0]["subject"] == "tennis?"
        assert seen == {"token": "tok-g", "max": 3}


@pytest.mark.asyncio
async def test_calendar_tool_reads_with_stored_grant(monkeypatch, tmp_path):
    from noesek import connectors
    from noesek.connectors import google as gtool

    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    store.put("google", "ethan-main", "tok-g", ("calendar.readonly",))

    async def fake_events(token, max_results):
        return [{"id": "e1", "summary": "Tennis with Sam",
                 "start": "2026-09-20T15:00:00-05:00", "end": "2026-09-20T16:00:00-05:00",
                 "location": "Buena Vista"}]

    monkeypatch.setattr(gtool, "list_events", fake_events)

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        no_grant = await c.get("/connectors/google/calendar/events", params={"chat_id": "nobody"})
        assert no_grant.status_code == 403
        r = await c.get("/connectors/google/calendar/events", params={"chat_id": "ethan-main"})
        assert r.status_code == 200
        ev = r.json()["events"][0]
        assert ev["summary"] == "Tennis with Sam" and ev["location"] == "Buena Vista"


@pytest.mark.asyncio
async def test_github_tool_reads_with_stored_grant(monkeypatch, tmp_path):
    from noesek import connectors
    from noesek.connectors import github as ghtool

    store = connectors.TokenStore(tmp_path / "connectors.json")
    monkeypatch.setattr(connectors, "default_store", lambda: store)
    store.put("github", "ethan-main", "tok-gh", ("repo",))

    async def fake_notes(token, max_results):
        return [{"id": "n1", "repo": "ethan/noesek-agent", "title": "CI green",
                 "type": "CheckSuite", "reason": "ci_activity",
                 "updated_at": "2026-09-20T15:00:00Z"}]

    monkeypatch.setattr(ghtool, "list_notifications", fake_notes)

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        no_grant = await c.get("/connectors/github/notifications", params={"chat_id": "nobody"})
        assert no_grant.status_code == 403
        r = await c.get("/connectors/github/notifications", params={"chat_id": "ethan-main"})
        assert r.status_code == 200
        assert r.json()["notifications"][0]["repo"] == "ethan/noesek-agent"


@pytest.mark.asyncio
async def test_computer_input_commands(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setattr(server.shutil, "which", lambda x: "/usr/bin/xdotool")

    calls = []

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        calls.append(cmd)
        return FakeProc()

    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", fake_exec)

    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as c:
        bad = await c.post("/computer/input", json={"action": "nuke"})
        assert bad.status_code == 400
        missing = await c.post("/computer/input", json={"action": "type"})
        assert missing.status_code == 400
        ok = await c.post("/computer/input", json={"action": "type", "text": "hi there"})
        assert ok.status_code == 200 and ok.json()["ok"] is True
        assert calls[-1][:2] == ("xdotool", "type") and calls[-1][-1] == "hi there"
        ok2 = await c.post("/computer/input", json={"action": "click", "x": 10, "y": 20, "button": 1})
        assert ok2.status_code == 200
        assert calls[-1] == ("xdotool", "mousemove", "10", "20", "click", "1")
        ok3 = await c.post("/computer/input", json={"action": "key", "keys": "ctrl+s"})
        assert ok3.status_code == 200
        assert calls[-1] == ("xdotool", "key", "--", "ctrl+s")
