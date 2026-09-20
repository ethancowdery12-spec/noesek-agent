"""Long-run task durability: interrupted tasks recover on restart."""

import pytest

from sqlalchemy import delete

from noesek.db import Conversation, Session, Task, init_db, migrate
from noesek.jobs import recover_interrupted


@pytest.fixture(autouse=True)
async def _clean_tasks():
    yield
    async with Session() as s:
        await s.execute(delete(Task))
        await s.execute(delete(Conversation))
        await s.commit()


async def _mk_task(status, attempts=0, max_attempts=3):
    async with Session() as s:
        conv = Conversation(channel="local", external_user_id="ethan-main")
        s.add(conv)
        await s.commit()
        t = Task(conversation_id=conv.id, title="research: cheap VMs",
                 status=status, payload={"kind": "note", "text": "hi"},
                 attempts=attempts, max_attempts=max_attempts)
        s.add(t)
        await s.commit()
        return t.id


@pytest.mark.asyncio
async def test_running_task_requeued():
    await init_db(); await migrate()
    tid = await _mk_task("running", attempts=1)
    out = await recover_interrupted()
    assert out == {"requeued": 1, "failed": 0}
    async with Session() as s:
        t = await s.get(Task, tid)
        assert t.status == "pending"
        assert "requeued" in t.last_error
        assert t.attempts == 1  # backoff math keeps the spent attempt


@pytest.mark.asyncio
async def test_final_attempt_zombie_fails_instead_of_looping():
    await init_db(); await migrate()
    tid = await _mk_task("running", attempts=3, max_attempts=3)
    out = await recover_interrupted()
    assert out == {"requeued": 0, "failed": 1}
    async with Session() as s:
        t = await s.get(Task, tid)
        assert t.status == "failed" and t.finished_at is not None


@pytest.mark.asyncio
async def test_healthy_states_untouched():
    await init_db(); await migrate()
    done = await _mk_task("done")
    pend = await _mk_task("pending")
    out = await recover_interrupted()
    assert out == {"requeued": 0, "failed": 0}
    async with Session() as s:
        assert (await s.get(Task, done)).status == "done"
        assert (await s.get(Task, pend)).status == "pending"
