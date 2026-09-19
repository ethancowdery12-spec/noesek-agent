"""read_file tool: UTF-8 text reads confined to an allowlisted root.

Uses the vendored upstream path-security helpers (MIT, Nous Research) for
traversal checks and root confinement. Default root: NOESEK_HOME/workspace.
Files over 200KB are refused (workers should not flood context).
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import settings
from ..vendor.hermes.tools.path_security import has_traversal_component, validate_within_dir

MAX_BYTES = 200_000


class ReadInput(BaseModel):
    path: str = Field(description="Path relative to the allowlisted workspace root")


def allowed_root() -> Path:
    raw = settings.local_read_root.strip()
    root = Path(raw) if raw else Path(os.environ.get("NOESEK_HOME", Path.home() / ".noesek")) / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


async def read_file(inp: ReadInput) -> dict:
    if has_traversal_component(inp.path):
        return {"error": "path traversal is not allowed"}
    target = (allowed_root() / inp.path).resolve()
    problem = validate_within_dir(target, allowed_root())
    if problem:
        return {"error": f"outside allowlisted root: {problem}"}
    if not target.is_file():
        return {"error": "not a file"}
    if target.stat().st_size > MAX_BYTES:
        return {"error": f"file exceeds {MAX_BYTES} bytes"}
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"error": "not UTF-8 text"}
    return {"path": inp.path, "chars": len(text), "content": text}
