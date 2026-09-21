from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from sqlalchemy import select
from ..core.memory_v2 import MEMORY_KINDS, deindex_memory, fts_search_ids, index_memory
from ..db import Session, Conversation, Memory, Task

class RememberInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    kind: str = Field(default="note", description="note, fact, preference, episode, handoff, or lesson")
class SupersedeInput(BaseModel):
    memory_id: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=2000)
    kind: str | None = Field(default=None, description="defaults to the superseded memory's kind")
class SwitchModelInput(BaseModel):
    model: str = Field(min_length=1, max_length=128, description="a configured model name, or 'default' to clear this chat's override")
class LibraryDocsInput(BaseModel):
    library: str = Field(min_length=1, max_length=128, description="library or framework name, e.g. 'next.js' or 'sqlalchemy'")
    question: str = Field(min_length=1, max_length=500, description="what you need from its docs")
    max_chars: int = Field(default=4000, ge=500, le=12000)
class HandoffInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000, description="session handoff recap for future sessions")
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
        if inp.kind not in MEMORY_KINDS:
            return {"error": f"kind must be one of {', '.join(MEMORY_KINDS)}"}
        async with Session() as s:
            m = Memory(conversation_id=conversation_id, content=inp.content, kind=inp.kind, source="conversation")
            s.add(m); await s.commit()
        await index_memory(m.id, m.content)
        return {"stored": True, "memory_id": m.id, "kind": m.kind}
    return f

def supersede_handler(conversation_id: int):
    async def f(inp: SupersedeInput):
        async with Session() as s:
            old = (await s.execute(select(Memory).where(Memory.id==inp.memory_id, Memory.conversation_id==conversation_id, Memory.active==True))).scalar_one_or_none()
            if not old: return {"error": f"Memory #{inp.memory_id} not found in this conversation"}
            kind = inp.kind or old.kind
            if kind not in MEMORY_KINDS:
                return {"error": f"kind must be one of {', '.join(MEMORY_KINDS)}"}
            new = Memory(conversation_id=conversation_id, content=inp.content, kind=kind,
                         source=old.source)
            s.add(new); await s.flush()
            old.active = False; old.superseded_by = new.id; await s.commit()
        await deindex_memory(old.id); await index_memory(new.id, new.content)
        return {"superseded": True, "old_memory_id": old.id, "memory_id": new.id, "kind": new.kind}
    return f

def library_docs_handler():
    """Context7 via MCP (roadmap item 12): resolve-library-id -> query-docs."""
    async def f(inp: LibraryDocsInput):
        from ..core.mcp_client import call_tool_text, mcp_servers, mcp_session, top_library_id
        servers = mcp_servers()
        if not servers:
            return {"error": "no MCP servers configured (Context7 disabled and NOESEK_MCP_EXTRA_SERVERS empty)"}
        try:
            async with mcp_session(servers[0]) as session:
                resolved = await call_tool_text(session, "resolve-library-id",
                                                {"query": inp.question, "libraryName": inp.library})
                lib_id = top_library_id(resolved)
                if not lib_id:
                    return {"error": f"no Context7 match for '{inp.library}'", "candidates": resolved[:600]}
                docs = await call_tool_text(session, "query-docs",
                                            {"libraryId": lib_id, "query": inp.question})
        except Exception as e:  # network/SDK failures surface as a clean tool error
            return {"error": f"Context7 request failed: {type(e).__name__}: {str(e)[:200]}"}
        return {"library_id": lib_id, "docs": docs[: inp.max_chars], "server": servers[0].name}
    return f

def handoff_handler(conversation_id: int):
    """agentmemory idea (Apache-2.0): an explicit handoff skill - a recap the next session always sees."""
    async def f(inp: HandoffInput):
        return await memory_handler(conversation_id)(RememberInput(content=inp.content, kind="handoff"))
    return f

def switch_model_handler(conversation_id: int):
    """Per-chat model switching (multi-model layer). Only catalog models are allowed."""
    async def f(inp: SwitchModelInput):
        from ..core.llm import allowed_models, model_catalog
        name = inp.model.strip()
        async with Session() as s:
            conv = (await s.execute(select(Conversation).where(Conversation.id == conversation_id))).scalar_one_or_none()
            if not conv: return {"error": "conversation not found"}
            if name.lower() in {"default", "auto"}:
                conv.model_override = None; await s.commit()
                return {"switched": True, "model": model_catalog()["chat"],
                        "note": "override cleared; back to the default chat model"}
            if name not in allowed_models():
                return {"error": f"unknown model '{name}'. Configured: {', '.join(sorted(allowed_models()))}"}
            conv.model_override = name; await s.commit()
        return {"switched": True, "model": name,
                "note": "model switch drops the provider prefix cache; the next turn re-primes it"}
    return f

def recall_handler(conversation_id: int):
    async def f(inp: RecallInput):
        from ..core.context import rank_memories_async
        async with Session() as s:
            rows = (await s.execute(select(Memory).where(Memory.conversation_id==conversation_id, Memory.active==True))).scalars().all()
        picked = await rank_memories_async(conversation_id, inp.query, list(rows), inp.limit)
        return {"memories": [{"id": m.id, "kind": m.kind, "content": m.content} for m in picked]}
    return f

def forget_handler(conversation_id: int):
    async def f(inp: ForgetInput):
        async with Session() as s:
            m = (await s.execute(select(Memory).where(Memory.id==inp.memory_id, Memory.conversation_id==conversation_id, Memory.active==True))).scalar_one_or_none()
            if not m: return {"error": f"Memory #{inp.memory_id} not found in this conversation"}
            m.active = False; await s.commit()
        await deindex_memory(inp.memory_id)
        return {"forgotten": True, "memory_id": inp.memory_id}
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
