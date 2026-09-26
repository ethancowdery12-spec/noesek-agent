"""Offline gates for the code_review pipeline (open-code-review port)."""
import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from noesek.core.types import LLMReply, ToolCall
from noesek.review.diffparse import parse_unified_diff, render_file_diff
from noesek.review.grouping import group_files
from noesek.review.pipeline import (Comment, anchor_comment, dedupe_comments,
                                    filter_comments, format_markdown,
                                    review_group, run_review)
from noesek.tools.code_review import CodeReviewInput, code_review_handler

DIFF = """diff --git a/app/a.py b/app/a.py
index 1111111..2222222 100644
--- a/app/a.py
+++ b/app/a.py
@@ -1,4 +1,5 @@
 import os
+import sys
 def go(xs):
-    return xs[0]
+    return xs[0] if xs else None
 def stop():
     return 2
diff --git a/app/b.py b/app/b.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/app/b.py
@@ -0,0 +1,3 @@
+def f(x=[]):
+    x.append(1)
+    return x
diff --git a/dead.py b/dead.py
deleted file mode 100644
index 4444444..0000000
--- a/dead.py
+++ /dev/null
@@ -1,2 +0,0 @@
-gone
-away
diff --git a/logo.png b/logo.png
index 5555555..6666666 100644
Binary files a/logo.png and b/logo.png differ
"""


# ------------------------------------------------------------- diffparse

def test_parse_multi_file_statuses_and_added_lines():
    files = {f.path: f for f in parse_unified_diff(DIFF)}
    assert set(files) == {"app/a.py", "app/b.py", "dead.py", "logo.png"}
    assert files["app/a.py"].status == "modified"
    assert files["app/b.py"].status == "added"
    assert files["dead.py"].status == "deleted"
    assert files["logo.png"].is_binary
    assert files["app/a.py"].added_lines == {2, 4}
    assert files["app/b.py"].added_lines == {1, 2, 3}
    assert files["dead.py"].added_lines == set()


def test_parse_rename_and_churn():
    diff = ("diff --git a/old.py b/new.py\nsimilarity index 90%\n"
            "rename from old.py\nrename to new.py\n"
            "--- a/old.py\n+++ b/new.py\n@@ -1,2 +1,2 @@\n keep\n-x\n+y\n")
    (f,) = parse_unified_diff(diff)
    assert f.status == "renamed" and f.path == "new.py" and f.old_path == "old.py"
    assert f.churn == 2 and f.added_lines == {2}


def test_render_roundtrip_truncates():
    fd = parse_unified_diff(DIFF)[0]
    out = render_file_diff(fd, max_lines=2)
    assert "@@ -1,4 +1,5 @@" in out and "diff truncated" in out


# -------------------------------------------------------------- grouping

def test_grouping_covers_every_file_once_and_caps():
    files = parse_unified_diff(DIFF)
    many = files + [type(files[0])(path=f"pkg/m{i}.py", hunks=files[0].hunks) for i in range(12)]
    groups = group_files(many, max_per_group=10)
    flat = [f.path for g in groups for f in g]
    assert sorted(flat) == sorted(f.path for f in many)
    assert all(len(g) <= 10 for g in groups)


# -------------------------------------------------------------- anchoring

def test_anchor_snaps_nearby_and_blanks_far_off():
    fd = parse_unified_diff(DIFF)[0]  # added lines {2, 4}
    c = Comment("app/a.py", 3, 3, "bug", "high", "x")
    anchor_comment(fd, c)
    assert (c.start_line, c.end_line) == (2, 2) or (c.start_line, c.end_line) == (4, 4)
    far = Comment("app/a.py", 900, 900, "bug", "high", "x")
    anchor_comment(fd, far)
    assert (far.start_line, far.end_line) == (0, 0)
    missing = Comment("nope.py", 1, 1, "bug", "low", "x")
    anchor_comment(None, missing)
    assert missing.start_line == 0


def test_dedupe_keeps_highest_severity():
    a = Comment("f.py", 10, 10, "bug", "low", "mutable default argument shared across calls")
    b = Comment("f.py", 11, 11, "bug", "high", "mutable default argument shared across calls!")
    out = dedupe_comments([a, b])
    assert len(out) == 1 and out[0].severity == "high"


# --------------------------------------------------------- pipeline (fake)

class ScriptedLLM:
    """Plays plan -> review-loop -> filter from a script of replies."""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    async def complete(self, messages, tools):
        self.seen.append(messages[-1].get("content", "") or "")
        assert self.script, f"unexpected extra call: {messages[-1]}"
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _tc(name, args, i=0):
    return ToolCall(id=f"call_{name}_{i}", name=name, arguments=args)


@pytest.mark.asyncio
async def test_review_loop_collects_comments_and_stops_at_finish(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.py").write_text("import os\nimport sys\ndef go(xs):\n    return xs[0] if xs else None\n")
    (tmp_path / "app" / "b.py").write_text("def f(x=[]):\n    x.append(1)\n    return x\n")
    files = [f for f in parse_unified_diff(DIFF) if f.added_lines and not f.is_binary and f.status != "deleted"]
    llm = ScriptedLLM([
        LLMReply(content="1. [medium] b.py mutable default"),                 # plan
        LLMReply(tool_calls=[_tc("file_read", {"path": "app/b.py"})]),        # review r1
        LLMReply(tool_calls=[
            _tc("submit_comment", {"path": "app/b.py", "start_line": 1, "end_line": 1,
                                   "category": "bug", "severity": "high",
                                   "content": "mutable default argument", "suggestion": "use None"}, 1),
            _tc("submit_comment", {"path": "outside.py", "start_line": 1, "end_line": 1,
                                   "category": "bug", "severity": "low", "content": "off-limits"}, 2),
        ]),                                                                    # review r2
        LLMReply(tool_calls=[_tc("finish", {"summary": "done"})]),            # review r3
        LLMReply(content='{"drop": []}'),                                     # filter
    ])
    result = await run_review(tmp_path, [files], files, llm, background="demo")
    assert len(result["comments"]) == 1                       # off-set file refused
    c = result["comments"][0]
    assert (c["path"], c["start_line"], c["severity"]) == ("app/b.py", 1, "high")
    assert result["group_summaries"] == ["done"]
    assert "mutable default" in llm.seen[1]  # plan text fed into the review prompt


@pytest.mark.asyncio
async def test_review_loop_bounded_when_model_never_finishes(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.py").write_text("x = 1\n")
    files = [f for f in parse_unified_diff(DIFF) if f.path == "app/a.py"]
    llm = ScriptedLLM([LLMReply(content="plan")] +
                      [LLMReply(tool_calls=[_tc("code_search", {"pattern": "go"})]) for _ in range(10)] +
                      [LLMReply(content='{"drop": []}')])
    comments, _ = await review_group(tmp_path, files, [], llm, "", "", max_rounds=3, max_comments=5)
    assert comments == []
    assert len(llm.seen) <= 3 + 3 + 1  # plan + 3 rounds (+tool echoes) bounded


@pytest.mark.asyncio
async def test_filter_drops_only_proven_wrong_and_survives_parse_failure():
    files = [f for f in parse_unified_diff(DIFF) if f.path == "app/b.py"]
    comments = [Comment("app/b.py", 1, 1, "bug", "high", "mutable default"),
                Comment("app/b.py", 2, 2, "style", "low", "nit")]
    llm = ScriptedLLM([LLMReply(content='{"drop": [{"index": 1, "reason": "line 2 appends fine"}]}')])
    kept, dropped = await filter_comments(files, comments, llm)
    assert [c.content for c in kept] == ["mutable default"]
    assert dropped[0]["reason"].startswith("line 2")
    llm2 = ScriptedLLM([LLMReply(content="not json at all")])
    kept2, dropped2 = await filter_comments(files, comments, llm2)
    assert len(kept2) == 2 and dropped2 == []


@pytest.mark.asyncio
async def test_plan_failure_degrades_to_no_plan(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.py").write_text("x = 1\n")
    files = [f for f in parse_unified_diff(DIFF) if f.path == "app/a.py"]
    llm = ScriptedLLM([RuntimeError("provider down"),
                       LLMReply(tool_calls=[_tc("finish", {"summary": "fine"})]),
                       LLMReply(content='{"drop": []}')])
    result = await run_review(tmp_path, [files], files, llm)
    assert result["comments"] == [] and result["group_summaries"] == ["fine"]


# ------------------------------------------------------------ formatting

def test_markdown_groups_by_severity_and_clean_case():
    res = {"files_reviewed": ["a.py", "b.py"], "comments": [
        {"path": "a.py", "start_line": 4, "end_line": 4, "category": "bug",
         "severity": "high", "content": "real defect", "suggestion": "fix it"},
        {"path": "b.py", "start_line": 0, "end_line": 0, "category": "style",
         "severity": "low", "content": "nit", "suggestion": ""}],
        "dropped_by_filter": [], "group_summaries": []}
    md = format_markdown(res)
    assert "1 high" in md and "### High" in md and "`a.py:4`" in md
    assert "(unanchored)" not in md.split("### High")[1]  # low not rendered
    clean = format_markdown({"files_reviewed": ["a.py"], "comments": [], "dropped_by_filter": [], "group_summaries": []})
    assert "no critical, high, or medium issues" in clean


# ------------------------------------------------- chat tool end-to-end

def _git(repo: Path, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, env={"PATH": "/usr/bin:/bin",
                                             "GIT_CONFIG_NOSYSTEM": "1",
                                             "HOME": str(repo)})


@pytest.mark.asyncio
async def test_tool_end_to_end_over_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_INTERPRETER_DIR", str(tmp_path))
    ws = tmp_path / "77"
    ws.mkdir()
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    (ws / "m.py").write_text("def f():\n    return 1\n")
    _git(ws, "add", ".")
    _git(ws, "commit", "-qm", "init")
    (ws / "m.py").write_text("def f(x=[]):\n    x.append(1)\n    return x\n")

    llm = ScriptedLLM([
        LLMReply(content="1. [high] mutable default"),
        LLMReply(tool_calls=[
            _tc("submit_comment", {"path": "m.py", "start_line": 1, "end_line": 1,
                                   "category": "bug", "severity": "high",
                                   "content": "mutable default argument", "suggestion": "default None"}),
            _tc("finish", {"summary": "one issue"})]),
        LLMReply(content='{"drop": []}'),
    ])

    async def resolver():
        return llm

    handler = code_review_handler(77, resolver)
    out = await handler(CodeReviewInput(background="demo change"))
    assert out["ok"] and out["files_reviewed"] == ["m.py"]
    assert out["comments"][0]["severity"] == "high"
    assert "### High" in out["markdown"]

    empty = await handler(CodeReviewInput(staged=True))  # nothing staged
    assert empty["ok"] and empty["comments"] == []


@pytest.mark.asyncio
async def test_tool_refuses_escape_and_non_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_INTERPRETER_DIR", str(tmp_path))
    (tmp_path / "5").mkdir()
    handler = code_review_handler(5, None)
    assert "workspace" in (await handler(CodeReviewInput(path="../x")))["error"]
    assert "no git repo" in (await handler(CodeReviewInput()))["error"]


def test_checklist_carries_diff_discipline_section():
    from noesek.review.checklist import DEFAULT_CHECKLIST, checklist_for
    assert "Diff discipline" in DEFAULT_CHECKLIST
    for marker in ("Drive-bys", "Restating comments", "Abstraction cosplay", "Scope"):
        assert marker in DEFAULT_CHECKLIST
    # language append still composes on top
    assert "Diff discipline" in checklist_for(["x.py"])
    assert "Python traps" in checklist_for(["x.py"])
