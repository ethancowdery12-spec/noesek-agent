"""Noesek-authored bridge (NOT upstream Hermes source).

Only ``get_running_job_ids`` is provided: the vendored job store consults the
in-process scheduler's run-set for stale-claim liveness. Noesek's own worker
loop executes cron work, so the set is empty here. The full Hermes scheduler
tick is tracked in the v1.1 build report's next-stage ledger.
"""


def get_running_job_ids() -> set:
    return set()
