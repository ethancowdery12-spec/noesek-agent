"""Durable cron execution ledger backed by the vendored upstream cron persistence core.

Noesek's task queue claims and runs due tasks; this ledger records each attempt
as an upstream execution row (claim -> running -> completed/failed), deduplicates
scheduled occurrences, tracks recurring failures as incidents, and queues
result deliveries - all via the vendored Nous Research implementations (MIT).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..vendor.hermes.hermes_constants import set_hermes_home_override
from ..vendor.hermes.cron import delivery_queue, executions, incidents, occurrences


def default_home() -> Path:
    return Path(os.getenv("NOESEK_HOME", str(Path.home() / ".noesek")))


class CronLedger:
    """Process-wide handle over the vendored cron persistence databases.

    The vendored modules resolve their state directory from the upstream home
    override (a contextvar), so one ledger per process is the supported shape;
    constructing it pins the override to the Noesek home."""

    def __init__(self, home: str | Path | None = None):
        self.home = Path(home) if home else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        set_hermes_home_override(self.home)

    # --- occurrence identity ---
    @staticmethod
    def scheduled_instant(value: Any) -> str | None:
        return occurrences.scheduled_instant(value)

    @staticmethod
    def occurrence_completed(job: dict, instant: Any) -> bool:
        return occurrences.completed_occurrence(job, instant)

    # --- execution ledger ---
    @staticmethod
    def begin_attempt(job_id: str, *, source: str, scheduled_instant: Any = None) -> dict:
        return executions.create_execution(str(job_id), source=source, scheduled_instant=scheduled_instant)

    @staticmethod
    def mark_running(execution_id: str) -> dict | None:
        return executions.mark_execution_running(execution_id)

    @staticmethod
    def finish(execution_id: str, *, success: bool, error: str | None = None) -> dict | None:
        return executions.finish_execution(execution_id, success=success, error=error)

    @staticmethod
    def latest(job_id: str) -> dict | None:
        return executions.latest_execution(str(job_id))

    # --- incidents ---
    @staticmethod
    def record_failure(job_id: str, error: str, *, job_name: str | None = None) -> tuple[str, bool]:
        return incidents.upsert_incident(str(job_id), error, job_name=job_name)

    @staticmethod
    def list_incidents(state: str | None = None) -> list[dict]:
        return incidents.list_incidents(state)

    # --- result delivery ---
    @staticmethod
    def enqueue_delivery(execution_id: str, job: dict, content: str, *, for_failure: bool = False) -> dict:
        return delivery_queue.enqueue(execution_id, job, content, for_failure=for_failure)

    @staticmethod
    def claim_delivery() -> dict | None:
        return delivery_queue.claim_next()


class CronJobStore:
    """Noesek-facing durable cron job store over the vendored upstream cron/jobs.

    Real cron job CRUD with claim fencing, occurrence identity, and pause/resume,
    replacing Noesek's in-memory CronDispatcher for durable schedules. Execution
    stays with Noesek's task runner; this store owns schedule state."""

    def __init__(self, home: str | Path | None = None):
        CronLedger(home)  # pins the home override for the vendored modules

    @staticmethod
    def create(prompt: str, schedule: str, **kw) -> dict:
        from ..vendor.hermes.cron import jobs
        return jobs.create_job(prompt, schedule, **kw)

    @staticmethod
    def get(job_id: str) -> dict | None:
        from ..vendor.hermes.cron import jobs
        return jobs.get_job(str(job_id))

    @staticmethod
    def list() -> list[dict]:
        from ..vendor.hermes.cron import jobs
        return jobs.list_jobs()

    @staticmethod
    def pause(job_id: str, reason: str | None = None) -> dict | None:
        from ..vendor.hermes.cron import jobs
        return jobs.pause_job(str(job_id), reason=reason)

    @staticmethod
    def resume(job_id: str) -> dict | None:
        from ..vendor.hermes.cron import jobs
        return jobs.resume_job(str(job_id))

    @staticmethod
    def remove(job_id: str) -> bool:
        from ..vendor.hermes.cron import jobs
        return bool(jobs.remove_job(str(job_id)))

    @staticmethod
    def claim_for_fire(job_id: str, **kw):
        from ..vendor.hermes.cron import jobs
        return jobs.claim_job_for_fire(str(job_id), **kw)
