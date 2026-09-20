"""Agent-created files: a per-box outbox the agent writes and the user downloads.

Files land under ~/.noesek/files/ (NOESEK_FILES_DIR override for tests) via
the create_file controller tool; GET /files lists metadata and
GET /files/{name} downloads bytes. Names are sanitized - no traversal, no
absolute paths - and content is capped so a runaway agent cannot fill the disk.
"""
from __future__ import annotations

import os
import re
import time
from hashlib import sha256
from pathlib import Path

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_FILE_BYTES = 5_000_000


class FileStoreError(ValueError):
    pass


def files_dir() -> Path:
    override = os.environ.get("NOESEK_FILES_DIR")
    return Path(override) if override else Path.home() / ".noesek" / "files"


def _check_name(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise FileStoreError("invalid file name")
    return name


def write_file(name: str, content: str | bytes) -> dict:
    """Create or overwrite one file. Returns metadata, never the content."""
    _check_name(name)
    data = content.encode() if isinstance(content, str) else bytes(content)
    if not data:
        raise FileStoreError("empty content")
    if len(data) > MAX_FILE_BYTES:
        raise FileStoreError(f"file exceeds {MAX_FILE_BYTES} bytes")
    d = files_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    tmp = d / (name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return {"name": name, "bytes": len(data),
            "sha256": sha256(data).hexdigest(), "written_at": int(time.time())}


def read_file(name: str) -> bytes:
    _check_name(name)
    path = files_dir() / name
    if not path.is_file():
        raise FileStoreError("no such file")
    return path.read_bytes()


def list_files() -> list[dict]:
    d = files_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if p.is_file() and not p.name.endswith(".tmp"):
            data = p.read_bytes()
            out.append({"name": p.name, "bytes": len(data),
                        "sha256": sha256(data).hexdigest(),
                        "written_at": int(p.stat().st_mtime)})
    return out
