from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from sqlalchemy import select
from ..db import Session, Memory, Task

class RememberInput(BaseModel): content: str = Field(min_length=1, max_length=2000)
class RecallInput(BaseModel): query: str = Field(min_length=1, max_length=500); limit: int = Field(default=5, ge=1, le=20)
class ForgetInput(BaseModel): memory_id: int = Field(ge=1)
class CreateTaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    payload: dict = Field(default_factory=dict)
    run_in_seconds: int = Field(default=0, ge=0, le=7 * 24 * 3600)
class ListTasksInput(BaseModel): status: str | None = Field(default=None, description="pending, running, completed, failed, dead, or cancelled")
class CancelTaskInput(BaseModel): task_id: int = Field(ge=1)

def memory_handler(conversation_id: int):
    async def f(inp: RememberInput):
        async with Session() as s:
            m = Memory(conversation_id=conversation_id, content=inp.content); s.add(m); await s.commit()
            return {"stored": True, "memory_id": m.id}
    return f

def recall_handler(conversation_id: int):
    async def f(inp: RecallInput):
        from ..core.context import rank_memories
        async with Session() as s:
            rows = (await s.execute(select(Memory).where(Memory.conversation_id==conversation_id, Memory.active==True))).scalars().all()
        picked = rank_memories(inp.query, list(rows), inp.limit)
        return {"memories": [{"id": m.id, "content": m.content} for m in picked]}
    return f

def forget_handler(conversation_id: int):
    async def f(inp: ForgetInput):
        async with Session() as s:
            m = (await s.execute(select(Memory).where(Memory.id==inp.memory_id, Memory.conversation_id==conversation_id, Memory.active==True))).scalar_one_or_none()
            if not m: return {"error": f"Memory #{inp.memory_id} not found in this conversation"}
            m.active = False; await s.commit()
            return {"forgotten": True, "memory_id": m.id}
    return f

def task_handler(conversation_id: int):
    async def f(inp: CreateTaskInput):
        async with Session() as s:
            run_after = datetime.now(timezone.utc) + timedelta(seconds=inp.run_in_seconds)
            t = Task(conversation_id=conversation_id, title=inp.title, payload=inp.payload or {"kind": "note"}, run_after=run_after)
            s.add(t); await s.commit()
            return {"created": True, "task_id": t.id}
    return f

def list_tasks_handler(conversation_id: int):
    async def f(inp: ListTasksInput):
        async with Session() as s:
            q = select(Task).where(Task.conversation_id==conversation_id).order_by(Task.created_at.desc()).limit(20)
            if inp.status: q = select(Task).where(Task.conversation_id==conversation_id, Task.status==inp.status).order_by(Task.created_at.desc()).limit(20)
            rows = (await s.execute(q)).scalars().all()
        return {"tasks": [{"id": t.id, "title": t.title, "status": t.status, "attempts": t.attempts, "last_error": t.last_error[:200]} for t in rows]}
    return f

def cancel_task_handler(conversation_id: int):
    async def f(inp: CancelTaskInput):
        async with Session() as s:
            t = (await s.execute(select(Task).where(Task.id==inp.task_id, Task.conversation_id==conversation_id))).scalar_one_or_none()
            if not t: return {"error": f"Task #{inp.task_id} not found in this conversation"}
            if t.status not in ("pending", "running"): return {"error": f"Task #{t.id} is {t.status}; only pending or running tasks can be cancelled"}
            t.status = "cancelled"; t.finished_at = datetime.now(timezone.utc); await s.commit()
            return {"cancelled": True, "task_id": t.id}
    return f
