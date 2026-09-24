"""Tests for the Letta bounded core memory block (batch 3)."""
from noesek.core.context import assemble
from noesek.db import Conversation, Memory, Session
from noesek.tools.state import (
    RememberInput, SupersedeInput, memory_handler, supersede_handler,
)


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


async def test_core_kind_accepted_and_pinned(db):
    cid = await _conv()
    r = await memory_handler(cid)(RememberInput(content="the user prefers terse answers", kind="core"))
    assert r["kind"] == "core"
    async with Session() as s:
        out = await assemble(s, cid, query="completely unrelated zqxjv topic")
    system = out[0]["content"]
    assert "Core memory (always on, agent-curated):" in system
    assert "the user prefers terse answers" in system


async def test_core_block_editable_via_supersede(db):
    cid = await _conv()
    r1 = await memory_handler(cid)(RememberInput(content="deploy target is staging", kind="core"))
    await supersede_handler(cid)(SupersedeInput(memory_id=r1["memory_id"], content="deploy target is production"))
    async with Session() as s:
        out = await assemble(s, cid, query="zqxjv")
    system = out[0]["content"]
    assert "deploy target is production" in system
    assert "deploy target is staging" not in system


async def test_core_block_char_bound(db, monkeypatch):
    from noesek.core import context as ctx
    from noesek.config import settings
    monkeypatch.setattr(settings, "core_memory_max_chars", 40)
    cid = await _conv()
    await memory_handler(cid)(RememberInput(content="first fact that is quite long indeed", kind="core"))
    await memory_handler(cid)(RememberInput(content="second fact that pushes past the bound", kind="core"))
    async with Session() as s:
        out = await assemble(s, cid, query="zqxjv")
    block = out[0]["content"].split("Core memory (always on, agent-curated):\n", 1)[1]
    assert "first fact" in block
    assert "second fact" not in block  # bound trims whole lines, oldest-first kept


async def test_no_core_no_block(db):
    cid = await _conv()
    async with Session() as s:
        out = await assemble(s, cid, query="zqxjv")
    assert "Core memory" not in out[0]["content"]
