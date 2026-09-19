"""Conservative git worktree audit, following upstream worktree semantics (MIT patterns).

Never deletes: trees with uncommitted tracked changes, branches with unique
unpushed commits, trees in use, main/master/develop branches.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and ".git" not in p.parts[len(path.parts):]:
                total += p.stat().st_size
        except OSError:
            pass
    return total


def list_worktrees(repo: Path) -> list[dict]:
    out = _git(["worktree", "list", "--porcelain"], repo)
    trees = []
    current: dict = {}
    for line in out.splitlines() + ["worktree "]:
        if line.startswith("worktree "):
            if current:
                trees.append(current)
            if line == "worktree ":
                break
            current = {"path": line.split(" ", 1)[1], "branch": None, "commit": None}
        elif line.startswith("HEAD "):
            current["commit"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            current["branch"] = line.split("/", 2)[-1]
    main = Path(repo).resolve()
    merged = set()
    try:
        base = "main" if _git(["rev-parse", "--verify", "main"], repo) else "master"
        merged = {b.strip().lstrip("*+ ") for b in _git(["branch", "--merged", base], repo).splitlines()}
    except RuntimeError:
        base = None
    for t in trees:
        p = Path(t["path"])
        t["is_main_worktree"] = p.resolve() == main
        t["size_bytes"] = _dir_size(p) if p.is_dir() else 0
        t["age"] = None
        try:
            t["age"] = _git(["show", "-s", "--format=%ci", "HEAD"], p).strip()
        except RuntimeError:
            pass
        branch = t.get("branch")
        if t["is_main_worktree"]:
            verdict, reason = "keep", "main worktree"
        elif branch in {"main", "master", "develop"}:
            verdict, reason = "keep", "protected branch"
        elif branch and base and branch in merged:
            try:
                dirty = bool(_git(["status", "--porcelain"], p).strip())
            except RuntimeError:
                dirty = True
            if dirty:
                verdict, reason = "keep", "uncommitted changes"
            else:
                verdict, reason = "prunable", "clean and fully merged"
        else:
            verdict, reason = "keep", "unique or unmerged work"
        t["verdict"], t["reason"] = verdict, reason
    return trees


def prune(repo: Path, *, dry_run: bool = True, yes: bool = False) -> dict:
    trees = list_worktrees(repo)
    prunable = [t for t in trees if t["verdict"] == "prunable"]
    plan = [{"path": t["path"], "branch": t["branch"], "size_bytes": t["size_bytes"]} for t in prunable]
    if dry_run or not yes:
        return {"dry_run": True, "would_prune": plan,
                "confirm": "rerun with --yes to remove clean, fully-merged trees"}
    removed = []
    for t in plan:
        _git(["worktree", "remove", t["path"]], repo)
        removed.append(t)
    return {"dry_run": False, "pruned": removed}
