"""Tests for the conversation condenser (skills batch 3: OpenHands patterns,
own-words)."""
from sqlalchemy import select

from noesek.core.condenser import (dedupe_repeated_tool_calls,
                                   mask_tool_results, update_condensation)
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

def _acall(cid, name, args):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": cid, "type": "function",
                            "function": {"name": name, "arguments": args}}]}


def _tres(cid, content):
    return {"role": "tool", "tool_call_id": cid, "content": content}


def test_dedupe_masks_repeated_calls_keeps_latest():
    # roadmap item 97 (G10DC/chisel idea, own words): identical call repeated
    # across turns -> earlier results masked, the most recent stays verbatim.
    msgs = [_acall("c1", "search", '{"q":"a"}'), _tres("c1", "result one"),
            {"role": "user", "content": "again"},
            _acall("c2", "search", '{"q":"a"}'), _tres("c2", "result two")]
    out = dedupe_repeated_tool_calls(msgs)
    assert out[1]["content"].startswith("[duplicate tool call omitted")
    assert "search" in out[1]["content"] and "10 chars" in out[1]["content"]
    assert out[4]["content"] == "result two"
    assert msgs[1]["content"] == "result one"  # caller's dicts untouched
    assert dedupe_repeated_tool_calls(out) == out  # idempotent


def test_dedupe_distinct_calls_untouched():
    msgs = [_acall("c1", "search", '{"q":"a"}'), _tres("c1", "r1"),
            _acall("c2", "search", '{"q":"b"}'), _tres("c2", "r2"),
            _acall("c3", "lookup", '{"q":"a"}'), _tres("c3", "r3")]
    assert dedupe_repeated_tool_calls(msgs) is msgs


def test_dedupe_never_transforms_code_wholesale_mask_only():
    # chisel constraint: code/regex/literals are never re-compressed - a
    # duplicate result is masked whole or left verbatim, nothing in between.
    code = "```python\nprint(1)\n```"
    msgs = [_acall("c1", "run", "{}"), _tres("c1", code),
            _acall("c2", "run", "{}"), _tres("c2", code)]
    out = dedupe_repeated_tool_calls(msgs)
    assert out[1]["content"].startswith("[duplicate tool call omitted")
    assert code not in out[1]["content"]
    assert out[3]["content"] == code
