"""Tranche-10 foundations: fallback LLM, pool, heartbeat, memory search, postmortem, read_file."""
import json

import pytest


async def test_fallback_llm_failover_on_5xx(monkeypatch):
    from noesek.core import llm as llm_mod

    calls = []

    class FakeResp:
        def __init__(self, status, body=None):
            self.status_code = status; self._body = body or {}; self.text = json.dumps(self._body)

        def raise_for_status(self):
            if self.status_code >= 400:
                import httpx
                raise httpx.HTTPStatusError("err", request=None, response=None)

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, json=None, headers=None):
            calls.append(url)
            if "primary" in url:
                return FakeResp(503)
            return FakeResp(200, {"choices": [{"message": {"content": "from fallback", "tool_calls": []}}]})

    monkeypatch.setattr(llm_mod.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(llm_mod.settings, "llm_max_retries", 0)
    monkeypatch.setattr(llm_mod.asyncio, "sleep", _no_sleep)
    fb = llm_mod.FallbackLLM([{"base_url": "http://primary", "model": "m", "api_key": "k"},
                              {"base_url": "http://fallback", "model": "m", "api_key": "k"}])
    reply = await fb.complete([{"role": "user", "content": "hi"}], [])
    assert reply.content == "from fallback"
    assert any("primary" in u for u in calls) and any("fallback" in u for u in calls)


async def _no_sleep(_):
    pass


async def test_llm_pool_bounds_concurrency():
    from noesek.core.llm_pool import LLMPool
    pool = LLMPool(1)
    async with pool:
        assert pool._sem.locked()
    assert pool.started == 1


def test_heartbeat_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_HOME", str(tmp_path))
    from noesek.core.heartbeat import beat, heartbeat_status
    beat("task-worker")
    status = heartbeat_status()
    assert status["task-worker"]["live"] and status["task-worker"]["age_seconds"] < 5


async def test_memory_search(db, monkeypatch, tmp_path):
    from noesek.core.memory_search import search_memories
    from noesek.db import Conversation, Memory, Session
    async with Session() as s:
        c = Conversation(channel="test", external_user_id="u")
        s.add(c); await s.flush()
        s.add(Memory(conversation_id=c.id, content="Ethan prefers short replies"))
        s.add(Memory(conversation_id=c.id, content="unrelated note"))
        await s.commit()
    hits = await search_memories("short replies")
    assert len(hits) == 1 and "Ethan" in hits[0]["content"]
    with pytest.raises(ValueError):
        await search_memories("   ")


def test_postmortem_from_incident(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from noesek.cli_ops import postmortem
    from cron import incidents
    inc_id, _ = incidents.upsert_incident("job-9", "Traceback: boom", job_name="nightly")
    text = postmortem(inc_id)
    assert "# Postmortem: job-9" in text and "boom" in text and "## Root cause" in text
    with pytest.raises(KeyError):
        postmortem("no-such-incident")


async def test_read_file_confined(tmp_path, monkeypatch):
    import noesek.config as cfg
    monkeypatch.setattr(cfg.settings, "local_read_root", str(tmp_path))
    (tmp_path / "note.txt").write_text("hello workspace")
    from noesek.tools.local_read import ReadInput, read_file
    ok = await read_file(ReadInput(path="note.txt"))
    assert ok["content"] == "hello workspace"
    bad = await read_file(ReadInput(path="../outside.txt"))
    assert "error" in bad
    missing = await read_file(ReadInput(path="nope.txt"))
    assert "error" in missing


def test_read_file_registered_for_workers():
    from noesek.workers.runner import _all_tool_specs
    assert "read_file" in _all_tool_specs()
