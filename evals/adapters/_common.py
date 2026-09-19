"""Shared helpers for Noesek eval adapters."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def out_dir() -> Path:
    if "--out" in sys.argv:
        d = Path(sys.argv[sys.argv.index("--out") + 1])
    else:
        d = Path(tempfile.mkdtemp(prefix="noesek-adapter-"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def emit(verdict: str, **details) -> None:
    print(json.dumps({"verdict": verdict, **details}, sort_keys=True))


def env_for(home: Path, **extra) -> dict:
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC),
        "NOESEK_HOME": str(home),
        "HERMES_HOME": str(home),
        "NOESEK_DATABASE_URL": f"sqlite+aiosqlite:///{home}/noesek.db",
    }
    env.update(extra)
    return env


def run_cli(home: Path, *args: str, timeout: int = 60, **extra_env) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "noesek.cli", *args],
        env=env_for(home, **extra_env), capture_output=True, text=True, timeout=timeout)
