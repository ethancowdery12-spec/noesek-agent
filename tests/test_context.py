from noesek.core.context import rank_memories, trim_to_budget, assemble
from noesek.db import Conversation, Memory, Message, Session

def _mem(mid, content, ts):
    from datetime import datetime, timezone
    m = Memory(conversation_id=1, content=content)
    m.id = mid; m.created_at = datetime.fromtimestamp(ts, timezone.utc)
    return m

def test_rank_memories_prefers_overlap_then_recency():
    ms = [_mem(1, "user likes dark mode", 100), _mem(2, "deploy host is a vps", 200), _mem(3, "user likes tea", 50)]
    ranked = rank_memories("what does the user like", ms, 2)
    assert ranked[0].content == "user likes dark mode"
    assert len(ranked) == 2

def test_trim_to_budget_drops_oldest_keeps_system():
    msgs = [{"role": "system", "content": "sys"}] + [{"role": "user", "content": "x" * 100} for _ in range(10)]
    out, removed = trim_to_budget(msgs, 350)
    assert out[0]["role"] == "system"
    assert sum(len(m["content"]) for m in out) <= 350
    assert removed >= 7

async def test_assemble_includes_ranked_memory_and_omission_note(db):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u"); s.add(c); await s.commit(); cid = c.id
        s.add(Memory(conversation_id=cid, content="favorite color is blue", active=True))
        for i in range(6): s.add(Message(conversation_id=cid, role="user", content="z" * 100))
        await s.commit()
        msgs = await assemble(s, cid, query="favorite color", char_budget=400)
    assert msgs[0]["role"] == "system"
    assert "favorite color is blue" in msgs[0]["content"]
    assert "older messages omitted" in msgs[0]["content"]
    assert sum(len(m["content"]) for m in msgs[1:]) <= 400
