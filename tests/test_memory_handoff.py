"""Roadmap item 39 (agentmemory, Apache-2.0): handoff/lesson memory kinds +
always-visible latest handoff. Patterns adopted, code is our own."""
from sqlalchemy import select

from noesek.core.context import assemble
from noesek.db import Conversation, Memory, Session
from noesek.tools.state import (
    HandoffInput, RememberInput, handoff_handler, memory_handler,
)


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


async def test_handoff_and_lesson_kinds_accepted(db):
    cid = await _conv()
    r1 = await memory_handler(cid)(RememberInput(content="shipped v3.2, eval gate green", kind="handoff"))
    assert r1["kind"] == "handoff"
    r2 = await memory_handler(cid)(RememberInput(content="never commit to main directly", kind="lesson"))
    assert r2["kind"] == "lesson"
    r3 = await memory_handler(cid)(RememberInput(content="x", kind="bogus"))
    assert "error" in r3


async def test_handoff_tool_forces_kind(db):
    cid = await _conv()
    r = await handoff_handler(cid)(HandoffInput(content="session ended mid-deploy; resume at step 3"))
    assert r["stored"] and r["kind"] == "handoff"
    async with Session() as s:
        m = (await s.execute(select(Memory).where(Memory.id == r["memory_id"]))).scalar_one()
        assert m.kind == "handoff"


async def test_latest_handoff_always_visible_in_context(db):
    cid = await _conv()
    await memory_handler(cid)(RememberInput(content="handoff: deploy paused at migrate step", kind="handoff"))
    async with Session() as s:
        out = await assemble(s, cid, query="completely unrelated zqxjv topic")
    system = out[0]["content"]
    assert "handoff: deploy paused at migrate step" in system


async def test_older_handoff_not_shown_when_superseded(db):
    cid = await _conv()
    from noesek.tools.state import SupersedeInput, supersede_handler
    r1 = await memory_handler(cid)(RememberInput(content="handoff: old plan", kind="handoff"))
    await supersede_handler(cid)(SupersedeInput(memory_id=r1["memory_id"], content="handoff: new plan"))
    async with Session() as s:
        out = await assemble(s, cid, query="zqxjv")
    system = out[0]["content"]
    assert "handoff: new plan" in system
    assert "handoff: old plan" not in system
