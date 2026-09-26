"""Deterministic grouping of changed files into review clusters.

Files in one directory usually change together for one reason, so grouping
by directory (largest churn first, chunked to a per-group cap) covers the
common case without spending a model call on it.
"""
from __future__ import annotations

from .diffparse import FileDiff

MAX_PER_GROUP = 10


def group_files(files: list[FileDiff], max_per_group: int = MAX_PER_GROUP) -> list[list[FileDiff]]:
    by_dir: dict[str, list[FileDiff]] = {}
    for f in files:
        d = f.path.rsplit("/", 1)[0] if "/" in f.path else "."
        by_dir.setdefault(d, []).append(f)
    groups: list[list[FileDiff]] = []
    for d in sorted(by_dir):
        members = sorted(by_dir[d], key=lambda f: f.path)
        for i in range(0, len(members), max_per_group):
            groups.append(members[i:i + max_per_group])
    groups.sort(key=lambda g: -sum(f.churn for f in g))
    return groups
