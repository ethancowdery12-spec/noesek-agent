"""Tool-result output caps with full local capture.

Large tool results flood the model context. Results over the cap are written
whole to NOESEK_HOME/captures/ (0600) and replaced by a small receipt that
references the capture file - data is never silently dropped.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

DEFAULT_CAP_BYTES = 20_000


def capture_dir() -> Path:
    root = Path(os.environ.get("NOESEK_HOME", Path.home() / ".noesek")) / "captures"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def cap_tool_result(result, *, cap_bytes: int = DEFAULT_CAP_BYTES,
                    directory: Path | None = None):
    """Return `result` unchanged when small enough; otherwise capture + receipt."""
    blob = json.dumps(result, ensure_ascii=False, default=str).encode()
    if len(blob) <= cap_bytes:
        return result
    digest = hashlib.sha256(blob).hexdigest()
    dest = (directory or capture_dir()) / f"{int(time.time())}-{digest[:16]}.json"
    dest.write_bytes(blob)
    dest.chmod(0o600)
    preview = blob[:cap_bytes].decode(errors="replace")
    return {"truncated": True, "cap_bytes": cap_bytes, "total_bytes": len(blob),
            "sha256": digest, "captured_to": str(dest), "preview": preview}
