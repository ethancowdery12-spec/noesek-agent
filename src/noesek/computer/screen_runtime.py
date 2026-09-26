"""Lifecycle for the noesek computer screen: a TigerVNC Xvnc desktop the agent's
computer tools act on and a human can watch and take over.

Design adapted from Nous Research hermes-agent tools/bot_desktop (MIT License; see
THIRD_PARTY_NOTICES): Xvnc as X server + RFB server in one process, listening only
on a 0600 Unix socket (no TCP port, no VNC password - only processes running as the
service user can reach it, and the WebSocket bridge in server.py is the authenticated
way in); Xvnc flags kept in sync with rfb_filter's assumptions.

Own implementation for noesek: no multi-profile state, env-based config, Xfce
components optional (a bare Xvnc already serves browser and screenshot tools).
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import screen_lease

log = logging.getLogger("noesek.computer.screen")

GEOMETRY = os.environ.get("NOESEK_SCREEN_GEOMETRY", "1440x900")
MIN_FREE_MEMORY_MB = int(os.environ.get("NOESEK_SCREEN_MIN_FREE_MEMORY_MB", "512"))
DISPLAY = os.environ.get("NOESEK_COMPUTER_DISPLAY", ":99")


def _dir() -> Path:
    d = screen_lease.state_dir() / "screen"
    d.mkdir(parents=True, exist_ok=True)
    return d


def socket_path() -> Path:
    return _dir() / "rfb.sock"


def pid_path() -> Path:
    return _dir() / "xvnc.pid"


def activity_path() -> Path:
    return _dir() / "activity"


def installed() -> bool:
    return shutil.which("Xvnc") is not None


def _free_memory_mb() -> int:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 1 << 30  # cannot tell: do not block on it


def _read_pid() -> int | None:
    try:
        return int(pid_path().read_text().strip())
    except (OSError, ValueError):
        return None


def running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return socket_path().exists()


def status() -> dict:
    lease = screen_lease.get()
    return {
        "installed": installed(),
        "running": running(),
        "display": DISPLAY if running() else "",
        "geometry": GEOMETRY,
        "control": screen_lease.public_view(lease),
        "free_memory_mb": _free_memory_mb(),
        "min_free_memory_mb": MIN_FREE_MEMORY_MB,
    }


def start() -> dict:
    """Start Xvnc on the Unix socket and publish DISPLAY. Idempotent."""
    if running():
        return status()
    if not installed():
        raise RuntimeError("Xvnc not installed (build the image with NOESEK_SCREEN=1)")
    if MIN_FREE_MEMORY_MB and _free_memory_mb() < MIN_FREE_MEMORY_MB:
        raise RuntimeError(
            f"not enough free memory for a screen ({_free_memory_mb()} MB < {MIN_FREE_MEMORY_MB} MB)")
    sock = socket_path()
    if sock.exists():
        sock.unlink()
    logf = open(_dir() / "xvnc.log", "ab")
    proc = subprocess.Popen(
        ["Xvnc", DISPLAY,
         "-geometry", GEOMETRY, "-depth", "24", "-dpi", "96",
         "-rfbport", "-1", "-rfbunixpath", str(sock), "-rfbunixmode", "0600",
         "-SecurityTypes", "None", "-AlwaysShared", "-AcceptSetDesktopSize",
         "-FrameRate", "30", "-SendCutText=0", "-MaxCutText", "262144"],
        stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_path().write_text(str(proc.pid))
    os.chmod(pid_path(), 0o600)
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Xvnc exited during startup; see screen/xvnc.log")
        if sock.exists():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Xvnc did not publish its socket in time")
    os.environ["DISPLAY"] = DISPLAY
    activity_path().touch()
    log.info("screen up on %s (pid %s, socket %s)", DISPLAY, proc.pid, sock)
    return status()


def stop(*, force: bool = False) -> dict:
    """Stop the screen. Refuses while a human holds control unless force (a runbook can
    never yank a live takeover)."""
    if screen_lease.human_holds() and not force:
        raise RuntimeError("a human holds control; stop refused without force")
    if force:
        screen_lease.release(unless_human=False)
    pid = _read_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    for p in (pid_path(), socket_path()):
        try:
            p.unlink()
        except OSError:
            pass
    return status()
