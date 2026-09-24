"""Tests for the conversation condenser (skills batch 3: OpenHands patterns,
own-words)."""
from sqlalchemy import select

from noesek.core.condenser import mask_tool_results, update_condensation
from noesek.core.context import assemble
from noesek.core.memory_v2 import record_compaction
from noesek.db import Conversation, Memory, Message, Session


def _tool_msgs(n, size=40):
    return ([{"role": "user", "content": "start"}]
            + [{"role": "tool", "tool_call_id": f"c{i}", "content": "x" * size} for i in range(n)]
            + [{"role": "assistant", "content": "done"}])


def test_mask_keeps_recent_results_verbatim():
    msgs = _tool_msgs(10)
    out = mask_tool_results(msgs, keep_full=3)
    masked = [m for m in out if m.get("role") == "tool" and m["content"].startswith("[earlier tool result omitted")]
    verbatim = [m for m in out if m.get("role") == "tool" and not m["content"].startswith("[earlier tool result omitted")]
    assert len(masked) == 7
    assert len(verbatim) == 3
    assert "40 chars" in masked[0]["content"]
    # non-tool messages untouched; caller's dicts not mutated
    assert out[0]["content"] == "start"
    assert msgs[1]["content"] == "x" * 40


def test_mask_idempotent_and_small_windows_untouched():
    msgs = _tool_msgs(3)
    assert mask_tool_results(msgs, keep_full=6) is msgs or mask_tool_results(msgs, 6) == msgs
    once = mask_tool_results(_tool_msgs(10), keep_full=3)
    assert mask_tool_results(once, keep_full=3) == once


async def _conv_with_span():
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1")
        s.add(c); await s.commit()
        ids = []
        for i, (role, text) in enumerate([("user", "plan the launch"),
                                          ("assistant", "drafted the launch plan v1"),
                                          ("user", "add pricing"),
                                          ("assistant", "added three pricing tiers")]):
            m = Message(conversation_id=c.id, role=role, content=text)
            s.add(m); await s.commit(); await s.refresh(m)
            ids.append(m.id)
        return c.id, ids


async def test_first_condensation_created(db):
    cid, ids = await _conv_with_span()
    await record_compaction(cid, removed=2, budget=12000,
                            oldest_dropped_id=ids[0], newest_dropped_id=ids[1])
    seen = {}
    async def fake_summarize(tx):
        seen["tx"] = tx
        return "launch plan v1 exists; pricing not yet added"
    mid = await update_condensation(cid, fake_summarize)
    assert mid is not None
    assert "plan the launch" in seen["tx"]
    async with Session() as s:
        mem = await s.get(Memory, mid)
        assert mem.kind == "condensation" and mem.active
        assert "launch plan v1 exists" in mem.content


async def test_rolling_chains_prior_summary_and_supersedes(db):
    cid, ids = await _conv_with_span()
    await record_compaction(cid, removed=2, budget=12000,
                            oldest_dropped_id=ids[0], newest_dropped_id=ids[1])
    async def s1(tx): return "first digest"
    first = await update_condensation(cid, s1)
    await record_compaction(cid, removed=2, budget=12000,
                            oldest_dropped_id=ids[2], newest_dropped_id=ids[3])
    seen = {}
    async def s2(tx):
        seen["tx"] = tx
        return "second digest"
    second = await update_condensation(cid, s2)
    assert second is not None and second != first
    assert "first digest" in seen["tx"]  # prior summary chained in
    assert "add pricing" in seen["tx"]   # new span included
    async with Session() as s:
        old = await s.get(Memory, first)
        new = await s.get(Memory, second)
        assert old.active is False and old.superseded_by == second
        assert new.active and "second digest" in new.content
    # idempotent: no new compactions -> None
    assert await update_condensation(cid, s2) is None


async def test_summarizer_failure_keeps_prior(db):
    cid, ids = await _conv_with_span()
    await record_compaction(cid, removed=2, budget=12000,
                            oldest_dropped_id=ids[0], newest_dropped_id=ids[1])
    async def boom(tx): raise RuntimeError("model down")
    assert await update_condensation(cid, boom) is None
    async def empty(tx): return ""
    assert await update_condensation(cid, empty) is None


async def test_condensation_pinned_in_context(db):
    cid, ids = await _conv_with_span()
    await record_compaction(cid, removed=2, budget=12000,
                            oldest_dropped_id=ids[0], newest_dropped_id=ids[1])
    async def s1(tx): return "the user is mid-launch with pricing done"
    await update_condensation(cid, s1)
    async with Session() as s:
        out = await assemble(s, cid, query="totally unrelated zqxjv")
    system = out[0]["content"]
    assert "the user is mid-launch with pricing done" in system
    assert "rolling condensation" in system
