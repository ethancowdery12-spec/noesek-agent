"""P3: long-conversation reminder stapled onto the latest user message."""
from noesek.core.context import LONG_REMINDER, assemble
from noesek.core import context
from noesek.db import Conversation, Message, Session


async def _mk_convo(n_user: int, end_with: str = "user") -> int:
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u")
        s.add(c)
        await s.commit()
        for i in range(n_user):
            s.add(Message(conversation_id=c.id, role="user", content=f"question {i}",
                          created_at=t0 + timedelta(seconds=i)))
        if end_with == "assistant":
            s.add(Message(conversation_id=c.id, role="assistant", content="answer",
                          created_at=t0 + timedelta(seconds=n_user)))
        await s.commit()
        return c.id


async def test_no_reminder_below_threshold(db, monkeypatch):
    monkeypatch.setattr(context.settings, "long_reminder_min_messages", 10)
    cid = await _mk_convo(5)
    async with Session() as s:
        msgs = await assemble(s, cid, query="q")
    assert LONG_REMINDER not in msgs[-1]["content"]


async def test_reminder_at_threshold(db, monkeypatch):
    monkeypatch.setattr(context.settings, "long_reminder_min_messages", 6)
    cid = await _mk_convo(6)
    async with Session() as s:
        msgs = await assemble(s, cid, query="q")
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"].endswith(LONG_REMINDER)
    assert msgs[-1]["content"].startswith("question 5")


async def test_reminder_disabled(db, monkeypatch):
    monkeypatch.setattr(context.settings, "long_reminder_min_messages", 2)
    monkeypatch.setattr(context.settings, "long_reminder_enabled", False)
    cid = await _mk_convo(8)
    async with Session() as s:
        msgs = await assemble(s, cid, query="q")
    assert LONG_REMINDER not in msgs[-1]["content"]


async def test_reminder_counts_beyond_history_limit(db, monkeypatch):
    # Total conversation messages drive the trigger, not the fetched window:
    # history_limit (24) must not mask a long chat.
    monkeypatch.setattr(context.settings, "long_reminder_min_messages", 30)
    cid = await _mk_convo(31)
    async with Session() as s:
        msgs = await assemble(s, cid, query="q")
    assert msgs[-1]["content"].endswith(LONG_REMINDER)


async def test_reminder_skipped_when_last_is_assistant(db, monkeypatch):
    monkeypatch.setattr(context.settings, "long_reminder_min_messages", 3)
    cid = await _mk_convo(4, end_with="assistant")
    async with Session() as s:
        msgs = await assemble(s, cid, query="q")
    assert msgs[-1]["role"] == "assistant"
    assert LONG_REMINDER not in msgs[-1]["content"]


def test_system_prompt_documents_reminder_trust():
    from noesek.core.context import SYSTEM
    assert "session-reminder" in SYSTEM
    assert "not from the user" in SYSTEM
