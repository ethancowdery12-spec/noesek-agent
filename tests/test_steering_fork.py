"""Stage H: live steering + session fork."""
import asyncio
from pydantic import BaseModel
from sqlalchemy import select

from noesek.core.controller import Controller
from noesek.core.steering import consume_steering, fork_conversation, steer
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Conversation, Memory, Message, Session
from noesek.testing import ScriptedLLM, tool_reply, text_reply


class Q(BaseModel): q: str = "x"


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


async def test_steering_note_injected_between_steps(db):
    cid = await _conv()
    async def search(inp):
        await steer(cid, "focus on recent results only")  # user steers mid-turn
        return {"results": []}
    def factory(c2):
        r = ToolRegistry(); r.register(ToolSpec("search", "d", Q, Risk.READ, search)); return r
    llm = ScriptedLLM([tool_reply("search", {"q": "x"}), text_reply("done")])
    c = Controller(llm=llm, registry_factory=factory)
    r = await c.handle(cid, "research")
    assert r.text == "done"
    second = llm.requests[1]["messages"]
    assert any(m["role"] == "user" and "focus on recent results only" in m["content"] for m in second)


async def test_steering_consumed_once(db):
    cid = await _conv()
    await steer(cid, "note")
    assert await consume_steering(cid) == ["note"]
    assert await consume_steering(cid) == []


async def test_fork_copies_messages_and_active_memories(db):
    cid = await _conv()
    async with Session() as s:
        s.add(Message(conversation_id=cid, role="user", content="hello"))
        s.add(Message(conversation_id=cid, role="assistant", content="hi"))
        s.add(Memory(conversation_id=cid, content="likes tea", kind="preference", active=True))
        s.add(Memory(conversation_id=cid, content="old fact", active=False))
        await s.commit()
    fork_id = await fork_conversation(cid, channel="cli", external_user_id="fork-1")
    async with Session() as s:
        msgs = (await s.execute(select(Message).where(Message.conversation_id == fork_id).order_by(Message.created_at))).scalars().all()
        mems = (await s.execute(select(Memory).where(Memory.conversation_id == fork_id))).scalars().all()
    assert [m.content for m in msgs] == ["hello", "hi"]
    assert len(mems) == 1 and mems[0].content == "likes tea" and mems[0].source == f"fork:{cid}"


async def test_fork_refuses_existing_destination(db):
    cid = await _conv()
    await fork_conversation(cid, channel="cli", external_user_id="fork-dup")
    import pytest
    with pytest.raises(ValueError):
        await fork_conversation(cid, channel="cli", external_user_id="fork-dup")
