"""Internal worker liveness heartbeats - no user-facing pings.

Each long-running loop beats into NOESEK_HOME/heartbeats/<name>.json;
`noesek status` surfaces the age so an operator can see a stuck worker.
Whether Noesek should ever ping the USER about progress is a separate
product decision; this mechanism is internal only.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _dir() -> Path:
    root = Path(os.environ.get("NOESEK_HOME", Path.home() / ".noesek")) / "heartbeats"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def beat(name: str) -> None:
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    (_dir() / f"{safe}.json").write_text(json.dumps({"name": name, "ts": time.time()}))


def heartbeat_status(max_age_seconds: float = 300) -> dict:
    now = time.time()
    out = {}
    for f in sorted(_dir().glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        age = round(now - data["ts"], 1)
        out[data["name"]] = {"age_seconds": age, "live": age <= max_age_seconds}
    return out
