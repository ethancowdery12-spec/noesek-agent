"""code_review: structured line-level review of git changes in the workspace.

Pipeline architecture adapted (own words) from alibaba/open-code-review
(Apache-2.0, see THIRD_PARTY_NOTICES.md): group changed files, plan risks,
review each group with a bounded context-tool loop, fact-check comments
against the diff, anchor to changed lines. Runs over the conversation code
workspace (the code_interpreter working directory); the model passes go
through the conversation's configured LLM.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from ..review.diffparse import parse_unified_diff
from ..review.grouping import group_files
from ..review.pipeline import format_markdown, run_review
from .interpreter import _session_root

_MAX_FILES = 25
_DIFF_CAP = 300_000
_EFFORT_ROUNDS = {"low": 3, "medium": 6, "high": 10}


class CodeReviewInput(BaseModel):
    path: str = Field(default=".", description="Git repo directory, relative to the conversation code workspace. Default: the workspace root.")
    commit: str = Field(default="", description="Review a single commit against its parent.")
    from_ref: str = Field(default="", description="Review the diff from this ref...")
    to_ref: str = Field(default="", description="...to this ref (default with from_ref: working tree).")
    staged: bool = Field(default=False, description="Review only staged changes.")
    background: str = Field(default="", max_length=1000, description="Optional business context: what this change is for. Improves review quality.")
    effort: str = Field(default="medium", description="low | medium | high - context-tool rounds per file group.")


async def _git_diff(repo: Path, inp: CodeReviewInput) -> tuple[int, str]:
    if inp.commit.strip():
        argv = ["git", "diff", f"{inp.commit.strip()}^", inp.commit.strip(), "--"]
    elif inp.from_ref.strip():
        to = inp.to_ref.strip()
        argv = ["git", "diff", inp.from_ref.strip()] + ([to] if to else []) + ["--"]
    elif inp.staged:
        argv = ["git", "diff", "--cached", "--"]
    else:
        argv = ["git", "diff", "HEAD", "--"]
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(repo))
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "git diff timed out"
    if proc.returncode != 0:
        return proc.returncode or 1, err.decode(errors="replace")[:500]
    return 0, out.decode(errors="replace")


def code_review_handler(conversation_id: int, llm_resolver):
    async def f(inp: CodeReviewInput) -> dict:
        rel = inp.path.strip() or "."
        if ".." in rel:
            return {"ok": False, "error": "path must stay inside the conversation workspace"}
        root = _session_root() / str(conversation_id)
        repo = (root / rel).resolve()
        try:
            repo.relative_to(root.resolve())
        except ValueError:
            return {"ok": False, "error": "path must stay inside the conversation workspace"}
        if not (repo / ".git").exists():
            return {"ok": False, "error": f"no git repo at {rel} - clone or git init in the workspace first (code_interpreter)"}
        rc, diff = await _git_diff(repo, inp)
        if rc != 0:
            return {"ok": False, "error": f"git diff failed: {diff}"}
        if len(diff) > _DIFF_CAP:
            return {"ok": False, "error": f"diff too large ({len(diff)} bytes); narrow with from_ref/to_ref or a subdirectory"}
        files = parse_unified_diff(diff)
        files = [fd for fd in files if not fd.is_binary and fd.status != "deleted" and fd.added_lines]
        if not files:
            return {"ok": True, "markdown": "No reviewable changes (nothing added or modified).",
                    "files_reviewed": [], "comments": []}
        omitted = max(0, len(files) - _MAX_FILES)
        files = files[:_MAX_FILES]
        effort = inp.effort.strip().lower()
        max_rounds = _EFFORT_ROUNDS.get(effort, _EFFORT_ROUNDS["medium"])
        llm = await llm_resolver()
        result = await run_review(repo, group_files(files), files, llm,
                                  background=inp.background.strip(),
                                  max_rounds=max_rounds)
        result["ok"] = True
        result["markdown"] = format_markdown(result)
        if omitted:
            result["note"] = f"{omitted} changed file(s) over the {_MAX_FILES}-file cap were not reviewed"
        return result
    return f
