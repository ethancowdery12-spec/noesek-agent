"""Noesek's cron tick: the vendored upstream job store owns schedule state; Noesek's
own task queue and controller execute the work.

Boundary: the upstream scheduler tick runs jobs through the upstream agent loop. Noesek
keeps its own orchestrator (per the reuse matrix), so a tick claims due jobs
from the vendored store - with the vendored fire fencing and occurrence dedup
intact - and enqueues them as durable Noesek tasks. Settlement (mark_job_run,
ledger finish) happens when the task completes.
"""
from __future__ import annotations

from sqlalchemy import select

from ..db import Session, Task
from .cron_store import CronJobStore, CronLedger


async def dispatch_due(conversation_id: int, home=None) -> list[dict]:
    """Claim due cron jobs from the vendored store and enqueue one durable task
    per job. Returns the dispatched job records. Idempotent across processes via
    the vendored claim fencing."""
    CronLedger(home)
    from ..vendor.hermes.cron import jobs
    dispatched = []
    for job in jobs.get_due_jobs():
        if jobs.is_terminal_job(job):
            continue
        claim = jobs.claim_job_for_fire(str(job["id"]), return_job=True)
        if not claim:
            continue
        claimed_job = claim if isinstance(claim, dict) else job
        ledger = CronLedger(home)
        attempt = ledger.begin_attempt(f"cron-{job['id']}", source="cron-tick",
                                       scheduled_instant=claimed_job.get("next_run_at"))
        async with Session() as s:
            t = Task(conversation_id=conversation_id,
                     title=f"cron: {claimed_job.get('name', job['id'])}",
                     payload={"kind": "cron", "job_id": str(job["id"]),
                              "execution_id": attempt["id"],
                              "instruction": claimed_job.get("prompt") or claimed_job.get("name", ""),
                              "notify": (claimed_job.get("deliver") or "local") != "none"})
            s.add(t); await s.commit()
        dispatched.append(claimed_job)
    return dispatched
