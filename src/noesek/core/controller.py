import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import select
from .approval_engine import assess_tool_arguments
from .context import assemble
from .llm import configured_llm
from .metrics import inc
from .tools import ToolRegistry, ToolSpec
from .types import Risk, TurnResult
from ..config import settings
from ..db import Approval, Message, Session, Task, now, record_trace
from ..tools.research import SearchInput, search_web
from ..tools.sandbox import PythonInput, run_python
from ..tools.state import (
    CancelTaskInput, CreateTaskInput, ForgetInput, ListTasksInput, RecallInput, RememberInput,
    cancel_task_handler, forget_handler, list_tasks_handler, memory_handler, recall_handler, task_handler,
)
from ..tools.web import FetchInput, fetch_url

MAX_STEPS = 8
APPROVAL_RISKS = {Risk.WRITE, Risk.EXTERNAL, Risk.MONEY, Risk.DESTRUCTIVE}

class DelegateInput(BaseModel):
    worker: Literal["researcher", "coder", "operator", "evaluator"]
    instruction: str = Field(min_length=1, max_length=4000)
    run_in_seconds: int = Field(default=0, ge=0, le=7 * 24 * 3600)
    notify: bool = Field(default=True, description="Send the worker result back to this conversation")

class Controller:
    def __init__(self, llm=None, registry_factory=None, max_steps: int = MAX_STEPS):
        self.llm = llm or configured_llm()
        self._registry_factory = registry_factory
        self.max_steps = max_steps

    def registry(self, conversation_id: int) -> ToolRegistry:
        if self._registry_factory: return self._registry_factory(conversation_id)
        t = settings.tool_timeout_seconds
        r = ToolRegistry()
        r.register(ToolSpec("remember","Store a durable user-approved fact or preference.",RememberInput,Risk.WRITE,memory_handler(conversation_id),timeout_seconds=t))
        r.register(ToolSpec("recall","Search durable memory for facts relevant to a query.",RecallInput,Risk.READ,recall_handler(conversation_id),timeout_seconds=t))
        r.register(ToolSpec("forget","Deactivate one durable memory by id.",ForgetInput,Risk.WRITE,forget_handler(conversation_id),timeout_seconds=t))
        r.register(ToolSpec("create_task","Create a durable background task.",CreateTaskInput,Risk.WRITE,task_handler(conversation_id),timeout_seconds=t))
        r.register(ToolSpec("list_tasks","List this conversation's background tasks and their status.",ListTasksInput,Risk.READ,list_tasks_handler(conversation_id),timeout_seconds=t))
        r.register(ToolSpec("cancel_task","Cancel a pending background task by id.",CancelTaskInput,Risk.WRITE,cancel_task_handler(conversation_id),timeout_seconds=t))
        r.register(ToolSpec("delegate_task","Delegate an instruction to a specialized background worker (researcher, coder, operator, evaluator).",DelegateInput,Risk.WRITE,self._delegate_handler(conversation_id),timeout_seconds=t))
        return r

    def _delegate_handler(self, conversation_id: int):
        async def f(inp: DelegateInput):
            async with Session() as s:
                t = Task(conversation_id=conversation_id, title=f"{inp.worker}: {inp.instruction[:120]}",
                         payload={"kind":"worker","worker":inp.worker,"instruction":inp.instruction,"notify":inp.notify},
                         run_after=datetime.now(timezone.utc)+timedelta(seconds=inp.run_in_seconds))
                s.add(t); await s.commit()
                return {"delegated": True, "task_id": t.id, "worker": inp.worker}
        return f

    async def handle(self, conversation_id: int, text: str, external_id: str | None = None) -> TurnResult:
        async with Session() as s:
            if external_id and (await s.execute(select(Message).where(Message.external_id==external_id))).scalar_one_or_none():
                return TurnResult(text="")
            s.add(Message(conversation_id=conversation_id, role="user", content=text, external_id=external_id)); await s.commit()
            messages = await assemble(s, conversation_id, query=text)
        await record_trace(conversation_id, "user_message", {"chars": len(text)})
        inc("noesek_turns_total")
        registry = self.registry(conversation_id); citations = []
        for _ in range(self.max_steps):
            reply = await self.llm.complete(messages, registry.schemas())
            if not reply.tool_calls:
                final = reply.content or "I could not produce a response."
                async with Session() as s: s.add(Message(conversation_id=conversation_id, role="assistant", content=final)); await s.commit()
                await record_trace(conversation_id, "final_reply", {"chars": len(final)})
                return TurnResult(text=final, citations=list(dict.fromkeys(citations)))
            messages.append({"role":"assistant","content":reply.content,"tool_calls":[{"id":c.id,"type":"function","function":{"name":c.name,"arguments":json.dumps(c.arguments)}} for c in reply.tool_calls]})
            for call in reply.tool_calls:
                inc("noesek_tool_calls_total")
                try: spec = registry.get(call.name)
                except KeyError: result = {"error": "unknown tool"}
                else:
                    if spec.risk in APPROVAL_RISKS:
                        gate = assess_tool_arguments(call.arguments)
                        if gate.blocked:
                            inc("noesek_approvals_blocked_total")
                            refusal = (f"Blocked by policy: {gate.reason}. This cannot be approved or run "
                                       "through the agent.")
                            async with Session() as s: s.add(Message(conversation_id=conversation_id, role="assistant", content=refusal)); await s.commit()
                            await record_trace(conversation_id, "approval_blocked", {"tool": call.name, "reason": gate.reason})
                            return TurnResult(text=refusal)
                        inc("noesek_approvals_total")
                        rationale = f"Requested during conversation turn: {text[:300]}"
                        if gate.verdict == "approval": rationale += f" (policy flag: {gate.reason})"
                        async with Session() as s:
                            a = Approval(conversation_id=conversation_id, tool_name=call.name, arguments=call.arguments,
                                         rationale=rationale,
                                         expires_at=now()+timedelta(hours=settings.approval_ttl_hours))
                            s.add(a); await s.commit()
                        prompt = (f"Approval required #{a.id}: {call.name} with {json.dumps(call.arguments, ensure_ascii=False)}. "
                                  f"Reply 'approve {a.id}' or 'reject {a.id}' within {settings.approval_ttl_hours:g}h.")
                        async with Session() as s: s.add(Message(conversation_id=conversation_id, role="assistant", content=prompt)); await s.commit()
                        await record_trace(conversation_id, "approval_required", {"approval_id": a.id, "tool": call.name})
                        return TurnResult(text=prompt, pending_approval_id=a.id)
                    try: result = await registry.invoke(call.name, call.arguments)
                    except Exception as e: result = {"error": type(e).__name__, "detail": str(e)[:500]}
                await record_trace(conversation_id, "tool_call", {"tool": call.name, "ok": not (isinstance(result, dict) and "error" in result)})
                for item in result.get("results",[]) if isinstance(result,dict) else []:
                    if isinstance(item, dict) and item.get("url"): citations.append(item["url"])
                if isinstance(result, dict) and result.get("url"): citations.append(result["url"])
                messages.append({"role":"tool","tool_call_id":call.id,"content":json.dumps(result,ensure_ascii=False)})
        await record_trace(conversation_id, "max_steps_stop", {})
        return TurnResult(text="I stopped after the maximum tool steps. Please narrow the request.", citations=citations)

    async def decide_approval(self, conversation_id: int, approval_id: int, approved: bool) -> TurnResult:
        async with Session() as s:
            a = (await s.execute(select(Approval).where(Approval.id==approval_id, Approval.conversation_id==conversation_id))).scalar_one_or_none()
            if not a: return TurnResult(text=f"Approval #{approval_id} was not found.")
            if a.status != "pending": return TurnResult(text=f"Approval #{approval_id} is already {a.status}.")
            if a.expires_at and a.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                a.status = "expired"; a.decided_at = now(); await s.commit()
                await record_trace(conversation_id, "approval_expired", {"approval_id": approval_id})
                return TurnResult(text=f"Approval #{approval_id} expired. Ask again to create a fresh one.")
            if not approved:
                a.status = "rejected"; a.decided_at = now(); await s.commit()
                await record_trace(conversation_id, "approval_rejected", {"approval_id": approval_id})
                return TurnResult(text=f"Rejected approval #{approval_id}.")
            gate = assess_tool_arguments(a.arguments or {})
            if gate.blocked:
                a.status = "blocked"; a.decided_at = now(); await s.commit()
                await record_trace(conversation_id, "approval_blocked", {"approval_id": approval_id, "reason": gate.reason})
                return TurnResult(text=f"Approval #{approval_id} cannot run: {gate.reason}. Hardline policy blocks it for everyone.")
            try:
                # Thin controller: approved WORK tools execute inside the operator
                # worker's scoped registry, never in the controller's own surface.
                from .orchestration import WORK_TOOLS
                if a.tool_name in WORK_TOOLS:
                    from ..workers.runner import worker_registry
                    result = await worker_registry("operator").invoke(a.tool_name, a.arguments)
                else:
                    result = await self.registry(conversation_id).invoke(a.tool_name, a.arguments)
                a.status = "executed"
            except Exception as e:
                result = {"error": type(e).__name__, "detail": str(e)[:500]}; a.status = "failed"
            a.decided_at = now(); await s.commit()
        await record_trace(conversation_id, f"approval_{a.status}", {"approval_id": approval_id})
        return TurnResult(text=f"Approval #{approval_id}: {a.status}. Result: {json.dumps(result, ensure_ascii=False)}")

    async def pending_approvals(self, conversation_id: int) -> TurnResult:
        async with Session() as s:
            rows = (await s.execute(select(Approval).where(Approval.conversation_id==conversation_id, Approval.status=="pending").order_by(Approval.created_at))).scalars().all()
        live = [a for a in rows if not a.expires_at or a.expires_at.replace(tzinfo=timezone.utc) >= datetime.now(timezone.utc)]
        if not live: return TurnResult(text="No pending approvals.")
        lines = [f"#{a.id}: {a.tool_name} with {json.dumps(a.arguments, ensure_ascii=False)[:200]}" for a in live]
        return TurnResult(text="Pending approvals:\n" + "\n".join(lines) + "\nReply 'approve ID' or 'reject ID'.")
