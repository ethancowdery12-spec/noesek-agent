from datetime import timedelta, timezone
from sqlalchemy import select
from noesek.db import Conversation, Message, Session, Task, now
from noesek.jobs import backoff_seconds, run_one

async def _conv():
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit(); return c.id

async def _task(cid, payload, **kw):
    async with Session() as s:
        t = Task(conversation_id=cid, title="t", payload=payload, **kw); s.add(t); await s.commit(); return t.id

async def _get(tid):
    async with Session() as s: return await s.get(Task, tid)

async def test_note_task_completes_and_notifies(db):
    cid = await _conv(); tid = await _task(cid, {"kind": "note", "note": "hello"})
    assert await run_one() is True
    t = await _get(tid)
    assert t.status == "completed" and t.result["note"] == "hello" and t.finished_at is not None
    async with Session() as s:
        msgs = (await s.execute(select(Message).where(Message.conversation_id == cid, Message.role == "assistant"))).scalars().all()
    assert any(f"task #{tid}" in m.content and "hello" in m.content for m in msgs)

async def test_future_task_not_claimed(db):
    cid = await _conv(); await _task(cid, {"kind": "note"}, run_after=now() + timedelta(hours=1))
    assert await run_one() is False

async def test_unknown_kind_retries_then_dead(db):
    cid = await _conv(); tid = await _task(cid, {"kind": "bogus"}, max_attempts=2)
    assert await run_one() is True
    t = await _get(tid)
    assert t.status == "pending" and "unknown task kind" in t.last_error and t.run_after.replace(tzinfo=timezone.utc) > now()
    async with Session() as s:
        t2 = await s.get(Task, tid); t2.run_after = now(); await s.commit()
    assert await run_one() is True
    t = await _get(tid)
    assert t.status == "dead" and t.finished_at is not None

async def test_worker_error_goes_dead_without_notify(db):
    cid = await _conv(); tid = await _task(cid, {"kind": "worker", "worker": "ghost", "instruction": "x"}, max_attempts=1)
    assert await run_one() is True
    t = await _get(tid)
    assert t.status == "dead" and "unknown worker" in t.last_error
    async with Session() as s:
        n = len((await s.execute(select(Message).where(Message.conversation_id == cid))).scalars().all())
    assert n == 0

async def test_deliver_callback_invoked(db):
    cid = await _conv(); await _task(cid, {"kind": "note", "note": "hi"})
    sent = []
    async def deliver(conv, text): sent.append((conv.external_user_id, text))
    assert await run_one(deliver=deliver) is True
    assert sent and sent[0][0] == "u1" and "hi" in sent[0][1]

def test_backoff_grows_exponentially():
    assert backoff_seconds(1) < backoff_seconds(2) < backoff_seconds(3)
