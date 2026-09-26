"""The review pipeline: plan -> bounded context-tool review loop -> filter.

Own implementation (Python) of the open-code-review stage architecture
(Apache-2.0; see THIRD_PARTY_NOTICES.md):

1. Plan pass: one model call lists the risk points of the group
   (location, nature, impact) to steer the review.
2. Review loop: the model reviews the group's diff with a bounded set of
   context tools (read a file, search the repo) and submits structured
   comments; every file in the group must get a pass before finish.
3. Filter pass: a separate fact-checker call may drop a comment ONLY when
   the diff proves it wrong. The asymmetry is deliberate: keeping a wrong
   comment costs seconds, dropping a real one loses the finding forever.
4. Anchoring + dedupe are deterministic: comments must land on lines the
   diff actually added, near-duplicates collapse to the highest severity.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .checklist import STANCE, checklist_for
from .diffparse import FileDiff, render_file_diff

CATEGORIES = ("bug", "security", "performance", "maintainability", "test", "style", "docs", "other")
SEVERITIES = ("critical", "high", "medium", "low")
_SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}

_READ_CAP = 12_000
_SEARCH_CAP = 40
_MAX_PATTERN = 120
_SNAP_RADIUS = 3


@dataclass
class Comment:
    path: str
    start_line: int
    end_line: int
    category: str
    severity: str
    content: str
    suggestion: str = ""

    def as_dict(self) -> dict:
        return {"path": self.path, "start_line": self.start_line,
                "end_line": self.end_line, "category": self.category,
                "severity": self.severity, "content": self.content,
                "suggestion": self.suggestion}


# ---------------------------------------------------------------- prompts

PLAN_SYSTEM = (
    "You plan code reviews. Given a diff, list the concrete risk points worth "
    "checking, worst first. For each: severity tag [high|medium|low], then one "
    "line covering WHERE it is, WHAT the problem might be, and WHY it matters. "
    "Only consider added or modified code; deleted code is context. If nothing "
    "stands out, say so plainly. No preamble, no markdown headers."
)

REVIEW_SYSTEM = f"""You are a code reviewer examining changes before merge. The diff shows what changed; use the context tools to read or search the surrounding code before judging - never assume what you cannot see.

{STANCE}

Rules:
- Review EVERY file in the review set; small or secondary files still get a pass.
- Comment only on files in the review set, only about added or modified lines. Deleted code and unchanged context are reference only.
- When you confirm a real issue, submit it with the submit_comment tool (one call per issue).
- Cross-file observations inside the set are encouraged: broken contracts, missing updates, inconsistencies.
- When every file has had its pass, call finish. Do not pad with nitpicks to look thorough."""

FILTER_SYSTEM = (
    "You fact-check code review comments against the diff they came from. "
    "Drop a comment ONLY when the diff proves it factually wrong - the code "
    "it describes says something else, or the line it cites does not exist. "
    "You are not judging usefulness or priority. When evidence falls short of "
    "proof, keep the comment: keeping a wrong one costs a few seconds, but "
    "dropping a real finding loses it forever. 'Suspicious', 'cannot verify', "
    "and 'I would not have raised this' all mean keep."
)

_TOOLS = [
    {"type": "function", "function": {
        "name": "file_read",
        "description": "Read a file from the repository for context (capped). Path is relative to the repo root.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "code_search",
        "description": "Search repository files with a regex; returns matching lines with paths (capped).",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "submit_comment",
        "description": "Submit one confirmed review finding on a file in the review set.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "content": {"type": "string", "description": "What the issue is and why it matters"},
            "suggestion": {"type": "string", "description": "Optional concrete fix"}},
            "required": ["path", "start_line", "end_line", "category", "severity", "content"]}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "End the review after every file in the review set has had a pass.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string"}}, "required": ["summary"]}}},
]


# ------------------------------------------------------------- tool impls

def _safe_path(repo: Path, rel: str) -> Path | None:
    try:
        p = (repo / rel).resolve()
        p.relative_to(repo.resolve())
    except (OSError, ValueError):
        return None
    return p if p.is_file() else None


def _file_read(repo: Path, rel: str) -> str:
    p = _safe_path(repo, rel)
    if p is None:
        return json.dumps({"error": "no such file in the repo (or path escapes it)"})
    try:
        text = p.read_text(errors="replace")
    except OSError as e:
        return json.dumps({"error": str(e)})
    if len(text) > _READ_CAP:
        text = text[:_READ_CAP] + "\n... [file truncated]"
    return json.dumps({"path": rel, "content": text})


def _code_search(repo: Path, pattern: str) -> str:
    if len(pattern) > _MAX_PATTERN:
        return json.dumps({"error": "pattern too long"})
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return json.dumps({"error": f"bad regex: {e}"})
    hits: list[dict] = []
    skipped = 0
    for p in sorted(repo.rglob("*")):
        if len(hits) >= _SEARCH_CAP:
            break
        if not p.is_file() or ".git" in p.parts:
            continue
        try:
            if p.stat().st_size > 512_000:
                skipped += 1
                continue
            for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append({"path": str(p.relative_to(repo)), "line": i,
                                 "text": line.strip()[:200]})
                    if len(hits) >= _SEARCH_CAP:
                        break
        except OSError:
            skipped += 1
    return json.dumps({"matches": hits, "files_skipped": skipped})


# ---------------------------------------------------------------- passes

async def _complete(llm, messages: list[dict], tools: list | None = None):
    return await llm.complete(messages, tools if tools is not None else [])


async def plan_group(group: list[FileDiff], llm, background: str) -> str:
    diffs = "\n\n".join(render_file_diff(f, max_lines=200) for f in group)
    user = f"Requirement background (optional): {background or '(none)'}\n\nDIFFS:\n{diffs}"
    try:
        reply = await _complete(llm, [{"role": "system", "content": PLAN_SYSTEM},
                                      {"role": "user", "content": user}])
    except Exception:
        return ""
    return (reply.content or "").strip()


async def review_group(repo: Path, group: list[FileDiff], other: list[str],
                       llm, background: str, plan: str,
                       max_rounds: int, max_comments: int) -> tuple[list[Comment], str]:
    review_paths = {f.path for f in group}
    diffs = "\n\n".join(render_file_diff(f) for f in group)
    others = "\n".join(other) if other else "(none)"
    user = (
        f"Other files changed in this update (not in your review set):\n{others}\n\n"
        f"<review_files>\n{diffs}\n</review_files>\n\n"
        f"Review checklist:\n{checklist_for(sorted(review_paths))}\n\n"
        f"Review plan (guidance, verify before trusting):\n{plan or '(none)'}\n\n"
        f"Requirement background: {background or '(none)'}\n\n"
        "Review the code changes in <review_files> now."
    )
    messages = [{"role": "system", "content": REVIEW_SYSTEM},
                {"role": "user", "content": user}]
    comments: list[Comment] = []
    summary = ""
    for _ in range(max_rounds):
        reply = await _complete(llm, messages, _TOOLS)
        if not reply.tool_calls:
            summary = (reply.content or "").strip()
            break
        messages.append({"role": "assistant", "content": reply.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.name,
                                                      "arguments": json.dumps(c.arguments)}}
                                        for c in reply.tool_calls]})
        done = False
        for call in reply.tool_calls:
            if call.name == "file_read":
                out = _file_read(repo, str(call.arguments.get("path", "")))
            elif call.name == "code_search":
                out = _code_search(repo, str(call.arguments.get("pattern", "")))
            elif call.name == "submit_comment":
                a = call.arguments
                path = str(a.get("path", ""))
                if path not in review_paths:
                    out = json.dumps({"error": f"{path} is not in the review set; comment refused"})
                elif len(comments) >= max_comments:
                    out = json.dumps({"error": "comment budget reached; call finish"})
                else:
                    sev = str(a.get("severity", "medium")).lower()
                    cat = str(a.get("category", "other")).lower()
                    comments.append(Comment(
                        path=path,
                        start_line=int(a.get("start_line") or 0),
                        end_line=int(a.get("end_line") or 0),
                        category=cat if cat in CATEGORIES else "other",
                        severity=sev if sev in SEVERITIES else "medium",
                        content=str(a.get("content", ""))[:2000],
                        suggestion=str(a.get("suggestion", ""))[:2000]))
                    out = json.dumps({"ok": True, "comments_so_far": len(comments)})
            elif call.name == "finish":
                summary = str(call.arguments.get("summary", ""))[:1000]
                out = json.dumps({"ok": True})
                done = True
            else:
                out = json.dumps({"error": f"unknown tool {call.name}"})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
        if done:
            break
    return comments, summary


async def filter_comments(group: list[FileDiff], comments: list[Comment], llm) -> tuple[list[Comment], list[dict]]:
    if not comments:
        return comments, []
    diffs = "\n\n".join(render_file_diff(f, max_lines=300) for f in group)
    listing = json.dumps([{"index": i, **c.as_dict()} for i, c in enumerate(comments)], indent=1)
    user = (f"DIFFS:\n{diffs}\n\nCOMMENTS:\n{listing}\n\n"
            'Return ONLY JSON: {"drop": [{"index": <int>, "reason": "<what in the diff proves it wrong>"}]}. '
            "Empty drop list means every comment stands.")
    try:
        reply = await _complete(llm, [{"role": "system", "content": FILTER_SYSTEM},
                                      {"role": "user", "content": user}])
        m = re.search(r"\{.*\}", reply.content or "", re.S)
        data = json.loads(m.group(0)) if m else {}
        drops = data.get("drop") or []
    except Exception:
        return comments, []
    dropped_idx: set[int] = set()
    dropped: list[dict] = []
    for d in drops:
        try:
            i = int(d.get("index"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= i < len(comments) and i not in dropped_idx:
            dropped_idx.add(i)
            dropped.append({"comment": comments[i].as_dict(),
                            "reason": str(d.get("reason", ""))[:400]})
    kept = [c for i, c in enumerate(comments) if i not in dropped_idx]
    return kept, dropped


# ------------------------------------------------------- anchoring/dedupe

def anchor_comment(fd: FileDiff | None, c: Comment) -> None:
    """Force the comment onto lines the diff added, or mark it unanchored (0/0)."""
    if fd is None or not fd.added_lines:
        c.start_line = c.end_line = 0
        return
    added = fd.added_lines
    if c.start_line in added:
        if c.end_line < c.start_line or c.end_line not in added:
            c.end_line = c.start_line
        return
    near = min(added, key=lambda n: abs(n - c.start_line), default=None)
    if near is not None and abs(near - c.start_line) <= _SNAP_RADIUS:
        c.start_line = c.end_line = near
    else:
        c.start_line = c.end_line = 0


def _norm(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", "", text.lower()).split())


def dedupe_comments(comments: list[Comment]) -> list[Comment]:
    kept: list[Comment] = []
    for c in sorted(comments, key=lambda c: _SEV_RANK[c.severity]):
        dupe = None
        for k in kept:
            if k.path != c.path:
                continue
            if k.start_line and c.start_line and abs(k.start_line - c.start_line) > 2:
                continue
            wa, wb = _norm(k.content), _norm(c.content)
            if wa and wb and len(wa & wb) / max(len(wa), len(wb)) >= 0.7:
                dupe = k
                break
        if dupe is None:
            kept.append(c)
    return kept


# ------------------------------------------------------------- orchestrate

async def run_review(repo: Path, groups: list[list[FileDiff]], all_files: list[FileDiff],
                     llm, background: str = "", max_rounds: int = 6,
                     max_comments: int = 20) -> dict:
    repo = repo.resolve()
    by_path = {f.path: f for f in all_files}
    all_paths = [f.path for f in all_files]
    out_comments: list[Comment] = []
    dropped: list[dict] = []
    summaries: list[str] = []
    for group in groups:
        other = [p for p in all_paths if p not in {f.path for f in group}]
        plan = await plan_group(group, llm, background)
        comments, summary = await review_group(
            repo, group, other, llm, background, plan, max_rounds, max_comments)
        if summary:
            summaries.append(summary)
        kept, group_dropped = await filter_comments(group, comments, llm)
        for c in kept:
            anchor_comment(by_path.get(c.path), c)
        out_comments.extend(kept)
        dropped.extend(group_dropped)
    out_comments = dedupe_comments(out_comments)
    out_comments.sort(key=lambda c: (_SEV_RANK[c.severity], c.path, c.start_line))
    return {
        "files_reviewed": all_paths,
        "comments": [c.as_dict() for c in out_comments],
        "dropped_by_filter": dropped,
        "group_summaries": summaries,
    }


def format_markdown(result: dict) -> str:
    comments = result["comments"]
    counts = {s: sum(1 for c in comments if c["severity"] == s) for s in SEVERITIES}
    lines = [f"Files reviewed: {len(result['files_reviewed'])}",
             f"Issues: {counts['critical']} critical, {counts['high']} high, "
             f"{counts['medium']} medium, {counts['low']} low", ""]
    if not any(counts[s] for s in ("critical", "high", "medium")):
        lines.append(f"Review complete - no critical, high, or medium issues found in "
                     f"{len(result['files_reviewed'])} files.")
        return "\n".join(lines)
    for sev in ("critical", "high", "medium"):
        group = [c for c in comments if c["severity"] == sev]
        if not group:
            continue
        lines.append(f"### {sev.capitalize()}")
        for c in group:
            loc = f"{c['path']}:{c['start_line']}" if c["start_line"] else f"{c['path']} (unanchored)"
            lines.append(f"- `{loc}` [{c['category']}] - {c['content']}")
            if c["suggestion"]:
                lines.append(f"  > Fix: {c['suggestion']}")
        lines.append("")
    return "\n".join(lines).strip()
