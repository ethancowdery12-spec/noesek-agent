"""Adapter for upstream evals/cron_error_diagnostics.py (Hermes c712f06d).

Upstream intent: when a cron job run fails, the persisted record must carry
the real traceback/reason (not a bare 'unknown failure'), and repeat failures
with the same error must dedup to one incident. Noesek target: the vendored
Hermes cron executions + incidents stores (local I/O only, no inference).
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, out_dir


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    import os
    os.environ.update({"NOESEK_HOME": str(home), "HERMES_HOME": str(home)})
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from cron import executions, incidents

    try:
        raise RuntimeError("provider setup failed: connection refused")
    except RuntimeError:
        tb = traceback.format_exc()

    ex = executions.create_execution("job-diag-1", source="adapter")
    executions.mark_execution_running(ex["id"])
    done = executions.finish_execution(ex["id"], success=False, error=tb)
    persisted = done and "connection refused" in (done.get("error") or "") and "Traceback" in done["error"]

    inc1, new1 = incidents.upsert_incident("job-diag-1", tb, job_name="diag")
    inc2, new2 = incidents.upsert_incident("job-diag-1", tb, job_name="diag")
    dedup = inc1 == inc2 and not new2
    listed = incidents.list_incidents(state="detected")
    listed_hit = any(i["id"] == inc1 for i in listed)

    ok = persisted and dedup and listed_hit
    emit("pass" if ok else "fail", traceback_persisted=persisted,
         incident_dedup=dedup, incident_listed=listed_hit, incident_id=inc1)


if __name__ == "__main__":
    main()
