"""Adapters added in v2.1: sessions admin/analysis, insights, dump, logs, pause, worktree."""
import json
from pathlib import Path

import pytest

from noesek import cli_ops, cli_surface
from noesek.compat import worktree_audit


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_HOME", str(tmp_path))
    return tmp_path


# --- pause/resume ------------------------------------------------------------

def test_pause_resume_roundtrip(home):
    assert cli_ops.is_paused() == {"paused": False}
    cli_ops.set_paused(True, "maintenance")
    state = cli_ops.is_paused()
    assert state["paused"] and state["reason"] == "maintenance" and state["since"]
    cli_ops.set_paused(False)
    assert cli_ops.is_paused() == {"paused": False}

def test_pause_resume_cli(home, capsys):
    assert cli_surface.main(["pause", "--reason", "deploy"]) == 0
    assert json.loads(capsys.readouterr().out)["paused"] is True
    assert cli_surface.main(["resume"]) == 0
    assert json.loads(capsys.readouterr().out)["paused"] is False

@pytest.mark.asyncio
async def test_worker_skips_when_paused(home, monkeypatch):
    from noesek import jobs
    calls = []

    async def fake_run_one(deliver=None):
        calls.append(1)
        return False

    monkeypatch.setattr(jobs, "run_one", fake_run_one)
    cli_ops.set_paused(True)
    import asyncio
    stop = asyncio.Event()

    async def stop_soon():
        await asyncio.sleep(0.3)
        stop.set()

    await asyncio.gather(jobs.task_worker(stop, poll_seconds=0.05), stop_soon())
    assert calls == []


# --- sessions admin + analysis ------------------------------------------------

@pytest.mark.asyncio
async def test_rename_prune_stats(home):
    from noesek.cli import _conversation
    from noesek.core.controller import Controller

    cid = await _conversation("admin-test")
    result = await Controller().handle(cid, "hello session")
    assert result.text

    row = await cli_ops.session_rename(cid, "deploy analysis")
    assert row["title"] == "deploy analysis"
    listed = await cli_ops.sessions_list()
    assert listed[0]["title"] == "deploy analysis"

    stats = await cli_ops.session_stats(cid)
    assert stats["turns"] == 1 and stats["messages"]["user"] == 1
    assert stats["input_tokens"] >= 0 and "tools" in stats

    store = await cli_ops.sessions_store_stats()
    assert store["sessions"] >= 1 and store["messages"] >= 2

    plan = await cli_ops.sessions_prune(0, yes=False, keep_min=0)
    assert cid in plan["would_prune"] and "confirm" in plan
    done = await cli_ops.sessions_prune(0, yes=True, keep_min=0)
    assert cid in done["pruned"]
    with pytest.raises(LookupError):
        await cli_ops.session_export(cid, home / "gone.json")


def test_sessions_stats_cli(home, capsys):
    assert cli_surface.main(["sessions", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "sessions" in payload and "messages" in payload


# --- insights / dump / logs ----------------------------------------------------

@pytest.mark.asyncio
async def test_insights_report(home):
    from noesek.cli import _conversation
    from noesek.core.controller import Controller

    cid = await _conversation("insights-test")
    await Controller().handle(cid, "count me in")
    report = await cli_ops.insights_report(7)
    assert report["total_turns"] >= 1
    assert sum(report["turns_per_day"].values()) == report["total_turns"]
    assert report["messages_total"] >= 2

def test_dump_report_redacted(home):
    import asyncio
    report = asyncio.run(cli_ops.dump_report())
    assert report["noesek_version"] and report["config"] and "paused" in report
    assert "sk-" not in json.dumps(report)

def test_logs_empty_and_tail(home, capsys):
    assert cli_surface.main(["logs"]) == 0
    assert "no log files" in capsys.readouterr().out
    logs = home / "logs"
    logs.mkdir()
    (logs / "agent.log").write_text("\n".join(f"line {i}" for i in range(100)))
    assert cli_surface.main(["logs", "agent.log", "-n", "5"]) == 0
    assert "line 99" in capsys.readouterr().out
    assert cli_surface.main(["logs", "../secrets"]) == 2


# --- worktree audit ------------------------------------------------------------

def _git(args, cwd):
    import subprocess
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(["init", "-q", "-b", "main"], r)
    _git(["config", "user.email", "t@t"], r)
    _git(["config", "user.name", "t"], r)
    (r / "f.txt").write_text("one")
    _git(["add", "."], r)
    _git(["commit", "-qm", "init"], r)
    return r


def test_worktree_list_and_prune(repo, tmp_path):
    _git(["worktree", "add", "-q", "-b", "wip", str(tmp_path / "wt-wip")], repo)
    _git(["worktree", "add", "-q", "-b", "merged-branch", str(tmp_path / "wt-merged")], repo)
    # dirty the wip tree: unique uncommitted work must be kept
    (tmp_path / "wt-wip" / "f.txt").write_text("changed")
    trees = worktree_audit.list_worktrees(repo)
    by_path = {Path(t["path"]).name: t for t in trees}
    assert by_path["repo"]["verdict"] == "keep"
    assert by_path["wt-wip"]["verdict"] == "keep"  # uncommitted changes
    assert by_path["wt-merged"]["verdict"] == "prunable"  # clean + merged

    plan = worktree_audit.prune(repo)
    assert plan["dry_run"] and [Path(p["path"]).name for p in plan["would_prune"]] == ["wt-merged"]
    done = worktree_audit.prune(repo, dry_run=False, yes=True)
    assert [Path(p["path"]).name for p in done["pruned"]] == ["wt-merged"]
    assert (tmp_path / "wt-wip").is_dir() and not (tmp_path / "wt-merged").exists()


def test_hermes_worktree_list_cli(repo, capsys):
    assert cli_surface.main(["worktree", "list", "--repo", str(repo)]) == 0
    assert "repo" in capsys.readouterr().out
