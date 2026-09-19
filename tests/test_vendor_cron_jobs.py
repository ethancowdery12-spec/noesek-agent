"""The vendored Hermes cron job store backs Noesek's durable schedules."""
from noesek.core.cron_store import CronJobStore


def test_job_crud_cycle(tmp_path):
    store = CronJobStore(tmp_path)
    job = store.create("say hi", "*/5 * * * *", name="greet")
    assert job["id"] and job["next_run_at"]
    assert len(store.list()) == 1
    store.pause(job["id"], reason="testing")
    assert store.get(job["id"])["paused_reason"] == "testing"
    store.resume(job["id"])
    assert not store.get(job["id"])["paused_at"]
    assert store.remove(job["id"]) is True
    assert store.list() == []

def test_oneshot_natural_schedule(tmp_path):
    store = CronJobStore(tmp_path)
    job = store.create("once", "in 5 minutes", name="one")
    assert job["schedule"]["kind"] == "once" and job["next_run_at"]

def test_claim_fencing(tmp_path):
    store = CronJobStore(tmp_path)
    job = store.create("say hi", "*/5 * * * *", name="fence")
    assert store.claim_for_fire(job["id"], force=True, return_job=True)
    # A second claim by the same caller while the first is live is refused.
    assert store.claim_for_fire(job["id"]) in (False, None)

def test_invalid_schedule_rejected(tmp_path):
    import pytest
    store = CronJobStore(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        store.create("bad", "not a schedule at all")
