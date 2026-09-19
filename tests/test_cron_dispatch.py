"""End to end: vendored schedule state -> Noesek task queue -> vendored settlement."""
import noesek.jobs as jobs
from noesek.core.cron_dispatch import dispatch_due
from noesek.core.cron_store import CronJobStore, CronLedger
from noesek.db import Conversation, Session, now
from noesek.workers import runner


async def test_due_cron_job_flows_through_task_queue(db, tmp_path, monkeypatch):
    async def fake_worker(role, instruction):
        return {"output": f"ran: {instruction}"}
    monkeypatch.setattr(jobs, "run_worker", fake_worker)
    monkeypatch.setattr(runner, "run_worker", fake_worker, raising=False)
    jobs._ledger = CronLedger(tmp_path)
    try:
        store = CronJobStore(tmp_path)
        job = store.create("stretch reminder", "* * * * *", name="stretch")
        async with Session() as s:
            c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit()
            cid = c.id
        # trigger_job schedules the job for the next tick (the store's own API)
        from noesek.vendor.hermes.cron import jobs as cron_jobs
        assert cron_jobs.trigger_job(job["id"]) is not None
        dispatched = await dispatch_due(cid, home=tmp_path)
        assert [d["id"] for d in dispatched] == [job["id"]]
        # second tick: already claimed, nothing new
        assert await dispatch_due(cid, home=tmp_path) == []
        assert await jobs.run_one() is True
        refreshed = store.get(job["id"])
        assert refreshed["last_status"] in (None, "success", "ok") or refreshed["last_run_at"]
        latest = jobs._ledger.latest(f"cron-{job['id']}")
        assert latest["status"] == "completed"
    finally:
        jobs._ledger = None
