"""Noesek-authored bridge (NOT upstream Hermes source).

Upstream emits cron execution-state heartbeats to its health monitor. Noesek
records the same transition in its own trace log instead.
"""
import logging

logger = logging.getLogger("noesek.vendor.cron_health")


def emit_execution_state(record: dict) -> None:
    try:
        logger.info("cron execution %s -> %s", record.get("id"), record.get("status"))
    except Exception:
        pass
