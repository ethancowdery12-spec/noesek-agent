from sqlalchemy import select
from noesek.db import Conversation, Memory, Session, Task
from noesek.tools.state import (
    CancelTaskInput, CreateTaskInput, ForgetInput, ListTasksInput, RecallInput, RememberInput,
    cancel_task_handler, forget_handler, list_tasks_handler, memory_handler, recall_handler, task_handler,
)

async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id

async def test_remember_recall_forget(db):
    cid = await _conv()
    r = await memory_handler(cid)(RememberInput(content="likes green tea"))
    assert r["stored"]
    out = await recall_handler(cid)(RecallInput(query="green tea"))
    assert out["memories"] and out["memories"][0]["content"] == "likes green tea"
    f = await forget_handler(cid)(ForgetInput(memory_id=r["memory_id"]))
    assert f["forgotten"]
    out = await recall_handler(cid)(RecallInput(query="green tea"))
    assert out["memories"] == []

async def test_forget_scoped_to_conversation(db):
    cid = await _conv(); other = await _conv("u2")
    r = await memory_handler(cid)(RememberInput(content="secret"))
    f = await forget_handler(other)(ForgetInput(memory_id=r["memory_id"]))
    assert "error" in f

async def test_task_lifecycle_tools(db):
    cid = await _conv()
    created = await task_handler(cid)(CreateTaskInput(title="research x", run_in_seconds=60))
    assert created["created"]
    listed = await list_tasks_handler(cid)(ListTasksInput(status="pending"))
    assert listed["tasks"][0]["title"] == "research x"
    cancelled = await cancel_task_handler(cid)(CancelTaskInput(task_id=created["task_id"]))
    assert cancelled["cancelled"]
    listed = await list_tasks_handler(cid)(ListTasksInput(status="pending"))
    assert listed["tasks"] == []

async def test_cancel_only_pending(db):
    cid = await _conv()
    async with Session() as s:
        t = Task(conversation_id=cid, title="done", status="completed"); s.add(t); await s.commit(); tid = t.id
    out = await cancel_task_handler(cid)(CancelTaskInput(task_id=tid))
    assert "error" in out
