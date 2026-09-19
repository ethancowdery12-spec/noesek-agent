"""The vendored upstream cron persistence core backs Noesek's execution ledger."""
from datetime import datetime, timezone
from sqlalchemy import select
from noesek.core.cron_store import CronLedger
from noesek.db import Conversation, Session, Task, now
import noesek.jobs as jobs


def test_attempt_lifecycle(tmp_path):
    l = CronLedger(tmp_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    attempt = l.begin_attempt("job-7", source="test", scheduled_instant=now_iso)
    assert l.latest("job-7")["status"] == "claimed"
    l.mark_running(attempt["id"])
    l.finish(attempt["id"], success=True)
    assert l.latest("job-7")["status"] == "completed"

def test_occurrence_dedup(tmp_path):
    l = CronLedger(tmp_path)
    instant = datetime.now(timezone.utc).isoformat()
    attempt = l.begin_attempt("job-8", source="test", scheduled_instant=instant)
    l.mark_running(attempt["id"]); l.finish(attempt["id"], success=True)
    assert l.occurrence_completed({"id": "job-8", "name": "t"}, instant) is True
    assert l.occurrence_completed({"id": "job-8", "name": "t"},
                                  datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()) is False

def test_incident_redaction(tmp_path):
    l = CronLedger(tmp_path)
    iid, is_new = l.record_failure("job-9", "auth failed token=supersecretvalue123")
    assert is_new and "supersecretvalue123" not in str(l.list_incidents())

def test_delivery_idempotent_and_claimable(tmp_path):
    l = CronLedger(tmp_path)
    attempt = l.begin_attempt("job-10", source="test")
    d1 = l.enqueue_delivery(attempt["id"], {"id": "job-10"}, "done")
    d2 = l.enqueue_delivery(attempt["id"], {"id": "job-10"}, "done")
    assert d1["status"] == d2["status"] == "pending"
    claimed = l.claim_delivery()
    assert claimed["execution_id"] == attempt["id"]
    assert l.claim_delivery() is None

async def test_task_runner_records_ledger(db, tmp_path):
    jobs._ledger = CronLedger(tmp_path)
    try:
        async with Session() as s:
            c = Conversation(channel="cli", external_user_id="u1"); s.add(c); await s.commit()
            t = Task(conversation_id=c.id, title="t", payload={"kind": "note", "note": "hi"}); s.add(t); await s.commit()
            tid = t.id
        assert await jobs.run_one() is True
        latest = jobs._ledger.latest(f"task-{tid}")
        assert latest["status"] == "completed" and latest["source"] == "task-queue"
        assert jobs._ledger.claim_delivery() is not None
    finally:
        jobs._ledger = None
