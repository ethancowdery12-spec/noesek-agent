"""SQLite job queue between the controller and the Kaggle guardian relay
(docs/GUARDIAN_SERVING.md). Render free tier cannot host the checkpoint, so
the model lives in a polling Kaggle CPU kernel: the gate enqueues a job here,
the kernel long-polls /internal/guardian/jobs/next, scores, and posts the
verdict back. Jobs expire quickly (the gate is waiting on them); expired
jobs are skipped by the relay and swept. No credentials or conversation
content ever enter a job - only the guardian state string of the action
under review.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import uuid
import os

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guardian_jobs (
  id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  status TEXT NOT NULL,           -- pending | claimed | done
  result TEXT,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guardian_jobs_status ON guardian_jobs(status, created_at);
"""

DEFAULT_TTL_SECONDS = 120.0
_SWEEP_AFTER_SECONDS = 3600.0


def default_db_path() -> str:
    return os.path.join(tempfile.gettempdir(), "noesek_guardian_jobs.db")


class JobStore:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        con = sqlite3.connect(self._path)
        try:
            con.executescript(_SCHEMA)
        finally:
            con.close()

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def enqueue(self, state: str, ttl: float = DEFAULT_TTL_SECONDS) -> str:
        job_id = uuid.uuid4().hex
        now = time.time()
        with self._lock, self._con() as con:
            con.execute(
                "INSERT INTO guardian_jobs (id, state, status, result, created_at, expires_at)"
                " VALUES (?, ?, 'pending', NULL, ?, ?)",
                (job_id, state, now, now + ttl))
        return job_id

    def get(self, job_id: str) -> dict | None:
        with self._lock, self._con() as con:
            row = con.execute("SELECT * FROM guardian_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def claim_next(self) -> dict | None:
        """Oldest unexpired pending job, atomically marked claimed. None if empty."""
        now = time.time()
        with self._lock, self._con() as con:
            row = con.execute(
                "SELECT id FROM guardian_jobs WHERE status = 'pending' AND expires_at > ?"
                " ORDER BY created_at LIMIT 1", (now,)).fetchone()
            if row is None:
                return None
            con.execute("UPDATE guardian_jobs SET status = 'claimed' WHERE id = ?", (row["id"],))
            full = con.execute("SELECT * FROM guardian_jobs WHERE id = ?", (row["id"],)).fetchone()
        return dict(full)

    def complete(self, job_id: str, result: dict) -> bool:
        """Store the relay's verdict. False when the job is unknown or already done."""
        with self._lock, self._con() as con:
            cur = con.execute(
                "UPDATE guardian_jobs SET status = 'done', result = ?"
                " WHERE id = ? AND status IN ('pending', 'claimed')",
                (json.dumps(result), job_id))
            return cur.rowcount == 1

    def sweep(self) -> int:
        """Drop finished jobs and long-expired stragglers."""
        cutoff = time.time() - _SWEEP_AFTER_SECONDS
        with self._lock, self._con() as con:
            cur = con.execute(
                "DELETE FROM guardian_jobs WHERE status = 'done' OR expires_at < ?", (cutoff,))
            return cur.rowcount

    def counts(self) -> dict:
        now = time.time()
        with self._lock, self._con() as con:
            rows = con.execute("SELECT status, COUNT(*) c FROM guardian_jobs GROUP BY status").fetchall()
            live = con.execute(
                "SELECT COUNT(*) c FROM guardian_jobs WHERE status != 'done' AND expires_at > ?",
                (now,)).fetchone()["c"]
        out = {r["status"]: r["c"] for r in rows}
        out["live_open"] = live
        return out


_store: JobStore | None = None
_store_lock = threading.Lock()


def get_store(path: str = "") -> JobStore:
    """Process-wide store. `path` only applies on first call (tests construct
    JobStore directly instead)."""
    global _store
    with _store_lock:
        if _store is None:
            from ..config import settings
            _store = JobStore(path or settings.guardian_relay_db or default_db_path())
        return _store


def _reset_for_tests():
    global _store
    with _store_lock:
        _store = None
