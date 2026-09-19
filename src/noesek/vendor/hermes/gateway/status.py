"""Noesek-authored bridge (NOT upstream Hermes source).

POSIX process-liveness probes standing in for upstream gateway.status helpers
(Noesek targets Linux/macOS deployments; upstream's Windows ctypes path is
not needed and the gateway subsystem is not vendored).
"""
from __future__ import annotations

import os
from pathlib import Path


def _pid_exists(pid: int) -> bool:
    pid = int(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def get_process_start_time(pid: int) -> int | None:
    """Process start time in milliseconds since boot (Linux /proc), else None."""
    try:
        ticks = os.sysconf("SC_CLK_TCK")
        with open(f"/proc/{int(pid)}/stat") as fh:
            start_ticks = int(fh.read().rsplit(")", 1)[1].split()[19])
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        boot_ms = int((__import__("time").time() - uptime) * 1000)
        return boot_ms + int(start_ticks * 1000 / ticks)
    except Exception:
        return None
