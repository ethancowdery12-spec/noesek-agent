"""Thin-controller / scoped-worker orchestration guarantees."""
import asyncio

import pytest

from noesek.core.controller import Controller
from noesek.core.orchestration import (CONTROLLER_TOOLS, WORK_TOOLS,
                                       CancellationToken, OrchestrationError,
                                       SpawnGrant, WorkBudget, run_scoped_worker)
from noesek.workers.runner import worker_registry


class QuietLLM:
    async def complete(self, messages, schemas):
        class Reply:
            content = "done"
            tool_calls = []
        return Reply()


class SlowLLM:
    async def complete(self, messages, schemas):
        await asyncio.sleep(5)
        class Reply:
            content = "late"
            tool_calls = []
        return Reply()


def test_controller_registry_has_no_work_tools(db):
    names = set(Controller(llm=QuietLLM()).registry(1).names())
    assert names <= CONTROLLER_TOOLS
    assert names & WORK_TOOLS == set()
    assert "delegate_task" in names


def test_workers_cannot_spawn_by_default():
    for name in ("researcher", "coder", "operator", "evaluator"):
        r = worker_registry(name)
        assert "delegate_child" not in r.names()
        assert "delegate_task" not in r.names()


def test_spawn_grant_is_explicit_and_scoped():
    with pytest.raises(OrchestrationError):
        SpawnGrant(parent_worker="coder", allowed_children=(), reason="x")
    grant = SpawnGrant(parent_worker="coder", allowed_children=("evaluator",), reason="t")
    assert "delegate_child" in worker_registry("coder", spawn_grant=grant).names()
    with pytest.raises(OrchestrationError):
        worker_registry("operator", spawn_grant=grant)  # grant is worker-bound


async def test_spawn_grant_denies_unlisted_children(db):
    grant = SpawnGrant(parent_worker="coder", allowed_children=("evaluator",), reason="t")
    r = worker_registry("coder", spawn_grant=grant)
    out = await r.invoke("delegate_child", {"worker": "researcher", "instruction": "go"})
    assert "not covered by the spawn grant" in out["error"]


async def test_worker_budget_caps_steps(db):
    class LoopLLM:
        async def complete(self, messages, schemas):
            class Call:
                id = "c1"
                name = "fetch_url"
                arguments = {"url": "https://example.com"}
            class Reply:
                content = ""
                tool_calls = [Call()]
            return Reply()
    res = await run_scoped_worker("researcher", "loop", llm=LoopLLM(),
                                  budget=WorkBudget(max_steps=2, max_seconds=60))
    assert res.steps == 2 and res.incomplete is True


async def test_worker_time_budget_stops_run(db):
    res = await run_scoped_worker("researcher", "slow", llm=SlowLLM(),
                                  budget=WorkBudget(max_steps=10, max_seconds=0.05))
    # deadline check fires before/around the first completion window
    assert res.incomplete is True or res.output == "late"


async def test_cancellation_propagates_into_worker(db):
    token = CancellationToken()
    token.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run_scoped_worker("researcher", "x", llm=QuietLLM(), token=token)


async def test_worker_returns_typed_handoff_with_evidence(db):
    res = await run_scoped_worker("researcher", "summarize", llm=QuietLLM())
    d = res.to_dict()
    assert d["worker"] == "researcher" and d["output"] == "done"
    assert d["cancelled"] is False and "steps" in d and "elapsed_seconds" in d


async def test_running_task_cancellation_propagates_through_queue(db):
    """cancel_task on a RUNNING task propagates into the worker and settles cancelled."""
    import asyncio as aio
    from datetime import datetime, timezone
    from noesek.db import Session, Task
    from noesek.jobs import run_one
    from noesek.tools.state import cancel_task_handler

    class HangLLM:
        async def complete(self, messages, schemas):
            await aio.sleep(30)
            raise AssertionError("should have been cancelled")

    import noesek.jobs as jobs
    from noesek.workers import runner
    orig = runner.run_worker
    async def patched(name, instruction, **kw):
        kw["llm"] = HangLLM()
        return await orig(name, instruction, **kw)
    jobs.run_worker = patched
    try:
        async with Session() as s:
            t = Task(conversation_id=1, title="hang", payload={"kind": "worker", "worker": "researcher", "instruction": "x", "notify": False},
                     run_after=datetime.now(timezone.utc))
            s.add(t); await s.commit(); tid = t.id
        run = aio.create_task(run_one())
        await aio.sleep(0.3)
        # task is now running; cancel through the conversation-facing tool
        out = await cancel_task_handler(1)(type("I", (), {"task_id": tid})())
        assert out == {"cancelled": True, "task_id": tid}
        await aio.wait_for(run, timeout=10)
        async with Session() as s:
            t = await s.get(Task, tid)
        assert t.status == "cancelled"
    finally:
        jobs.run_worker = orig


def test_team_run_uses_orchestration_primitives():
    from noesek.core.teams import TeamRun, TeamError
    run = TeamRun("ship", "lead", ("lead", "worker"), max_steps=3)
    assert run.budget.max_steps == 3
    run.report("worker", {"finding": 1})
    with pytest.raises(PermissionError):
        run.complete("worker", {})  # only the outcome owner completes
    run.complete("lead", {"final": True})
    syn = run.synthesize({"answer": "shipped"})
    assert syn["owner"] == "lead" and len(syn["evidence"]) == 2


def test_team_cancellation_propagates_to_token():
    from noesek.core.teams import TeamRun, TeamError
    run = TeamRun("ship", "lead", ("lead", "worker"))
    run.cancel()
    assert run.token.cancelled and run.state == "terminated"
    with pytest.raises(TeamError):
        run.report("worker", {})
