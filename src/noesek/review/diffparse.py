"""Unified-diff parsing for the review pipeline.

Own implementation: builds the file/hunk model the pipeline needs and the
set of added line numbers per file, so review comments can be anchored to
lines that actually changed (comments on unchanged or deleted lines are a
known failure mode of diff review).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_HEADER_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str]] = field(default_factory=list)  # (tag, text); tag in + - ' '


@dataclass
class FileDiff:
    path: str
    old_path: str = ""
    status: str = "modified"  # added | modified | deleted | renamed
    is_binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def added_lines(self) -> set[int]:
        """New-file line numbers introduced or modified by this diff."""
        out: set[int] = set()
        for h in self.hunks:
            new_no = h.new_start
            for tag, _ in h.lines:
                if tag == "+":
                    out.add(new_no)
                    new_no += 1
                elif tag == " ":
                    new_no += 1
        return out

    @property
    def churn(self) -> int:
        return sum(1 for h in self.hunks for tag, _ in h.lines if tag in "+-")


def _strip_prefix(p: str) -> str:
    p = p.strip()
    if p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    for pre in ("a/", "b/"):
        if p.startswith(pre):
            return p[2:]
    return p


def parse_unified_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    hunk: Hunk | None = None
    for raw in text.splitlines():
        header = _HEADER_RE.match(raw)
        if header:
            cur = FileDiff(path=header.group(2), old_path=header.group(1))
            files.append(cur)
            hunk = None
            continue
        if cur is None:
            continue
        if raw.startswith("new file mode"):
            cur.status = "added"
        elif raw.startswith("deleted file mode"):
            cur.status = "deleted"
        elif raw.startswith("rename from "):
            cur.old_path = raw[len("rename from "):].strip()
            cur.status = "renamed"
        elif raw.startswith("rename to "):
            cur.path = raw[len("rename to "):].strip()
        elif raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            cur.is_binary = True
        elif raw.startswith("--- "):
            p = _strip_prefix(raw[4:])
            if p != "/dev/null":
                cur.old_path = p
        elif raw.startswith("+++ "):
            p = _strip_prefix(raw[4:])
            if p != "/dev/null":
                cur.path = p
        else:
            m = _HUNK_RE.match(raw)
            if m:
                hunk = Hunk(
                    old_start=int(m.group(1)), old_count=int(m.group(2) or 1),
                    new_start=int(m.group(3)), new_count=int(m.group(4) or 1))
                cur.hunks.append(hunk)
            elif hunk is not None and raw[:1] in ("+", "-", " "):
                hunk.lines.append((raw[0], raw[1:]))
    return [f for f in files if f.path]


def render_file_diff(fd: FileDiff, max_lines: int = 400) -> str:
    """Compact unified-diff rendering of one file for prompts."""
    out = [f"--- a/{fd.old_path or fd.path}", f"+++ b/{fd.path}"]
    n = 0
    truncated = False
    for h in fd.hunks:
        out.append(f"@@ -{h.old_start},{h.old_count} +{h.new_start},{h.new_count} @@")
        for tag, text in h.lines:
            n += 1
            if n > max_lines:
                truncated = True
                break
            out.append(f"{tag}{text}")
        if truncated:
            out.append("... [diff truncated]")
            break
    return "\n".join(out)
