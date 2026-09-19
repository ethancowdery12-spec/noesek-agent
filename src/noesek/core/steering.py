"""Live steering + session fork (v2, stage H).

steer() drops a note for an in-flight turn; the controller consumes pending
notes between tool steps, so a user can redirect a long turn without waiting
for it to finish. fork_conversation() copies messages and active memories
into a new conversation (resume = keep talking to the fork).
"""
from __future__ import annotations

from sqlalchemy import select

from ..db import Conversation, Memory, Message, Session, SteeringNote


async def steer(conversation_id: int, text: str) -> int:
    """Queue a steering note for the conversation's in-flight (or next) turn."""
    if not text.strip():
        raise ValueError("steering text is required")
    async with Session() as s:
        note = SteeringNote(conversation_id=conversation_id, text=text.strip()[:2000])
        s.add(note); await s.commit()
        return note.id


async def consume_steering(conversation_id: int) -> list[str]:
    """Drain pending notes (marks them consumed). Called between tool steps."""
    async with Session() as s:
        rows = (await s.execute(
            select(SteeringNote).where(SteeringNote.conversation_id == conversation_id,
                                       SteeringNote.consumed == False)
            .order_by(SteeringNote.created_at))).scalars().all()
        for r in rows:
            r.consumed = True
        if rows:
            await s.commit()
        return [r.text for r in rows]


async def fork_conversation(conversation_id: int, *, channel: str, external_user_id: str,
                            include_memories: bool = True) -> int:
    """Copy messages (+ active memories) into a new conversation. Returns its id."""
    async with Session() as s:
        if (await s.execute(select(Conversation).where(Conversation.channel == channel,
                                                       Conversation.external_user_id == external_user_id))).scalar_one_or_none():
            raise ValueError("destination conversation already exists")
        msgs = (await s.execute(select(Message).where(Message.conversation_id == conversation_id)
                                .order_by(Message.created_at))).scalars().all()
        fork = Conversation(channel=channel, external_user_id=external_user_id)
        s.add(fork); await s.flush()
        for m in msgs:
            s.add(Message(conversation_id=fork.id, role=m.role, content=m.content))
        if include_memories:
            mems = (await s.execute(select(Memory).where(Memory.conversation_id == conversation_id,
                                                         Memory.active == True))).scalars().all()
            for m in mems:
                s.add(Memory(conversation_id=fork.id, kind=m.kind, content=m.content,
                             source=f"fork:{conversation_id}"))
        await s.commit()
        return fork.id
