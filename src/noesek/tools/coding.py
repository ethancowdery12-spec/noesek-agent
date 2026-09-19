"""Coder worker tools (v2, stage E): aider-style edit protocol, repo map,
submit checklist. All file access is confined to the allowlisted workspace
root (same confinement as read_file). The delegation itself is approval-gated
at the controller; these tools never leave the local workspace.

Edit protocol: edits arrive as ordered SEARCH/REPLACE hunks. Each hunk
applies only when its search text matches the file exactly once; failed
hunks are reported and skipped (per-hunk salvage) so one bad hunk never
loses the good ones.
"""
from __future__ import annotations

import ast
from pathlib import Path

from pydantic import BaseModel, Field

from .local_read import allowed_root
from ..vendor.hermes.tools.path_security import has_traversal_component, validate_within_dir

MAX_BYTES = 400_000
MAP_MAX_CHARS = 12_000


def _confine(path: str) -> tuple[Path | None, str | None]:
    if has_traversal_component(path):
        return None, "path traversal is not allowed"
    target = (allowed_root() / path).resolve()
    problem = validate_within_dir(target, allowed_root())
    if problem:
        return None, f"outside allowlisted root: {problem}"
    return target, None


class EditHunk(BaseModel):
    search: str = Field(min_length=1, max_length=20000)
    replace: str = Field(max_length=20000)


class ApplyEditInput(BaseModel):
    path: str = Field(description="Path relative to the workspace root")
    edits: list[EditHunk] = Field(min_length=1, max_length=50)


async def apply_edit(inp: ApplyEditInput) -> dict:
    """Apply SEARCH/REPLACE hunks with per-hunk salvage."""
    target, problem = _confine(inp.path)
    if problem:
        return {"error": problem}
    if not target.is_file():
        return {"error": "not a file; use write_file to create files"}
    if target.stat().st_size > MAX_BYTES:
        return {"error": f"file exceeds {MAX_BYTES} bytes"}
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"error": "not UTF-8 text"}
    applied, failed = 0, []
    for i, hunk in enumerate(inp.edits):
        n = text.count(hunk.search)
        if n == 0:
            failed.append({"hunk": i, "reason": "search text not found"})
        elif n > 1:
            failed.append({"hunk": i, "reason": f"search text matches {n} times; make it more specific"})
        else:
            text = text.replace(hunk.search, hunk.replace, 1)
            applied += 1
    if applied:
        target.write_text(text, encoding="utf-8")
    return {"path": inp.path, "applied": applied, "failed": failed, "written": applied > 0}


class WriteFileInput(BaseModel):
    path: str = Field(description="Path relative to the workspace root")
    content: str = Field(max_length=MAX_BYTES)


async def write_file(inp: WriteFileInput) -> dict:
    target, problem = _confine(inp.path)
    if problem:
        return {"error": problem}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(inp.content, encoding="utf-8")
    return {"path": inp.path, "chars": len(inp.content), "written": True}


class RepoMapInput(BaseModel):
    subdirectory: str = Field(default="", description="limit the map to this subdirectory")
    max_chars: int = Field(default=MAP_MAX_CHARS, ge=500, le=50000)


def _python_signatures(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return []
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"  def {node.name}() :{node.lineno}")
        elif isinstance(node, ast.ClassDef):
            lines.append(f"  class {node.name} :{node.lineno}")
    return sorted(lines, key=lambda s: int(s.rsplit(":", 1)[1]))


_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".mypy_cache"}


async def repo_map(inp: RepoMapInput) -> dict:
    """Deterministic repo map: file list + Python def/class signatures."""
    root = allowed_root()
    if inp.subdirectory:
        root, problem = _confine(inp.subdirectory)
        if problem:
            return {"error": problem}
        if not root.is_dir():
            return {"error": "not a directory"}
    lines, files = [], 0
    for path in sorted(root.rglob("*")):
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        if not path.is_file():
            continue
        files += 1
        rel = str(path.relative_to(root))
        lines.append(rel)
        if path.suffix == ".py" and path.stat().st_size <= MAX_BYTES:
            lines.extend(_python_signatures(path))
        if sum(len(l) + 1 for l in lines) > inp.max_chars:
            lines.append("... [map truncated to budget]")
            break
    return {"root": str(root), "files": files, "map": "\n".join(lines)}


class SubmitInput(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    files_changed: list[str] = Field(min_length=1, max_length=100)
    verification: str = Field(min_length=1, max_length=4000,
                              description="What was run to verify (command) and the observed result (exit code, output tail)")
    limitations: str = Field(default="", max_length=2000)


async def submit(inp: SubmitInput) -> dict:
    """Structured submit checklist; the coder calls this last."""
    return {"submitted": True, "checklist": {
        "summary": inp.summary, "files_changed": inp.files_changed,
        "verification": inp.verification, "limitations": inp.limitations}}
