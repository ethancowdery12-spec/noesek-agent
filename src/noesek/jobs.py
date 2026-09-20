import asyncio, logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .config import settings
from .core.metrics import inc
from .db import Conversation, Message, Session, Task, now, record_trace
from .core.cron_store import CronLedger
from .workers.runner import run_worker

log = logging.getLogger("noesek.jobs")

_ledger = None
def ledger() -> CronLedger:
    global _ledger
    if _ledger is None: _ledger = CronLedger()
    return _ledger

BACKOFF_BASE_SECONDS = 5

def backoff_seconds(attempts: int) -> float:
    return BACKOFF_BASE_SECONDS * (2 ** max(0, attempts - 1))

async def _watch_cancellation(task_id: int, token) -> None:
    """Poll the task row and propagate a cancel request into the running worker."""
    while not token.cancelled:
        await asyncio.sleep(0.5)
        async with Session() as s:
            t = await s.get(Task, task_id)
            if t is None or t.status == "cancelled":
                token.cancel()


async def execute_task(task: Task, token=None) -> dict:
    kind = (task.payload or {}).get("kind", "note")
    if kind == "note":
        return {"note": task.payload.get("note", task.title)}
    if kind == "worker":
        from .core.orchestration import WorkBudget
        budget = WorkBudget(max_seconds=settings.worker_max_seconds) if hasattr(settings, "worker_max_seconds") else WorkBudget()
        return await run_worker(task.payload.get("worker", "operator"), task.payload.get("instruction", task.title),
                                budget=budget, token=token)
    if kind == "cron":
        return await run_worker("operator", task.payload.get("instruction", task.title))
    if kind == "message":
        return {"message": task.payload.get("text", "")}
    raise ValueError(f"unknown task kind: {kind}")

async def claim_pending(session) -> Task | None:
    return (await session.execute(
        select(Task).where(Task.status=="pending", Task.run_after<=now()).order_by(Task.run_after)
        .with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()

async def run_one(deliver=None) -> bool:
    """Claim, execute, and settle one due task. Returns True when a task ran."""
    async with Session() as s:
        task = await claim_pending(s)
        if not task: return False
        task.status = "running"; task.attempts += 1; await s.commit()
    job_id = f"task-{task.id}"
    attempt = ledger().begin_attempt(job_id, source="task-queue", scheduled_instant=task.run_after)
    ledger().mark_running(attempt["id"])
    from .core.orchestration import CancellationToken
    token = CancellationToken()
    watcher = asyncio.create_task(_watch_cancellation(task.id, token))
    try:
        result = await execute_task(task, token=token)
        if isinstance(result, dict) and "error" in result and "output" not in result:
            raise RuntimeError(result["error"])
    except asyncio.CancelledError:
        ledger().finish(attempt["id"], success=False, error="cancelled")
        async with Session() as s:
            t = await s.get(Task, task.id)
            t.status = "cancelled"; t.finished_at = now()
            t.result = {"cancelled": True}
            await s.commit()
        await record_trace(task.conversation_id, "task_cancelled", {"task_id": task.id})
        return True
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:400]}"
        ledger().finish(attempt["id"], success=False, error=err)
        if (task.payload or {}).get("kind") == "cron":
            try:
                from cron import jobs as _cron_jobs
                if task.attempts >= (task.max_attempts or settings.task_max_attempts):
                    _cron_jobs.mark_job_run(task.payload["job_id"], success=False, error=err)
                if task.payload.get("execution_id"):
                    ledger().finish(task.payload["execution_id"], success=False, error=err)
            except Exception:
                log.warning("cron settle failed for task %s", task.id, exc_info=True)
        async with Session() as s:
            t = await s.get(Task, task.id)
            t.last_error = err
            if t.attempts < (t.max_attempts or settings.task_max_attempts):
                t.status = "pending"; t.run_after = now() + timedelta(seconds=backoff_seconds(t.attempts))
            else:
                t.status = "dead"; t.finished_at = now(); inc("noesek_tasks_dead_total")
                ledger().record_failure(job_id, err, job_name=task.title[:120])
            await s.commit()
        await record_trace(task.conversation_id, "task_failed", {"task_id": task.id, "error": err})
        log.warning("task %s failed: %s", task.id, err)
        return True
    finally:
        watcher.cancel()
        try:
            await watcher
        except BaseException:
            pass
    ledger().finish(attempt["id"], success=True)
    if (task.payload or {}).get("kind") == "cron":
        try:
            from cron import jobs as _cron_jobs
            _cron_jobs.mark_job_run(task.payload["job_id"], success=True)
            if task.payload.get("execution_id"):
                ledger().finish(task.payload["execution_id"], success=True)
        except Exception:
            log.warning("cron settle failed for task %s", task.id, exc_info=True)
    async with Session() as s:
        t = await s.get(Task, task.id)
        t.status = "completed"; t.result = result if isinstance(result, dict) else {"value": result}; t.finished_at = now()
        await s.commit()
    inc("noesek_tasks_completed_total")
    await record_trace(task.conversation_id, "task_completed", {"task_id": task.id})
    if (task.payload or {}).get("notify", True):
        text = _notification_text(task, result)
        ledger().enqueue_delivery(attempt["id"], {"id": job_id, "title": task.title}, text)
        async with Session() as s:
            s.add(Message(conversation_id=task.conversation_id, role="assistant", content=text))
            conv = await s.get(Conversation, task.conversation_id)
            await s.commit()
        if deliver and conv: await deliver(conv, text)
    return True

def _notification_text(task: Task, result: dict) -> str:
    body = ""
    if isinstance(result, dict):
        body = result.get("output") or result.get("message") or result.get("note") or str(result)[:800]
        cites = result.get("citations") or []
        if cites: body += "\nSources: " + ", ".join(cites[:5])
    return f"Background task #{task.id} ({task.title}) completed:\n{body}"[:3500]

async def task_worker(stop: asyncio.Event, deliver=None, poll_seconds: float | None = None):
    """Durable database-backed worker loop. Replace with Redis/Kafka only when scale requires it."""
    poll = poll_seconds or settings.worker_poll_seconds
    while not stop.is_set():
        from .core.heartbeat import beat
        beat("task-worker")
        from .cli_ops import is_paused
        if is_paused()["paused"]:  # global emergency stop (`noesek pause`): no new work starts
            try: await asyncio.wait_for(stop.wait(), timeout=poll)
            except TimeoutError: pass
            continue
        try:
            worked = await run_one(deliver=deliver)
        except Exception:
            log.exception("worker loop error"); worked = False
        if worked: continue
        try: await asyncio.wait_for(stop.wait(), timeout=poll)
        except TimeoutError: pass
