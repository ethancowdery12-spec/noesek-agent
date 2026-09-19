"""Stage E (core): aider-style edit protocol, repo map, submit checklist."""
import pytest

from noesek.tools.coding import (
    ApplyEditInput, EditHunk, RepoMapInput, SubmitInput, WriteFileInput,
    apply_edit, repo_map, submit, write_file,
)
from noesek.tools.local_read import allowed_root
from noesek.workers.runner import worker_registry


def _write(rel, text):
    p = allowed_root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


async def test_apply_edit_applies_unique_hunks():
    _write("proj/app.py", "def a():\n    return 1\n\ndef b():\n    return 2\n")
    r = await apply_edit(ApplyEditInput(path="proj/app.py", edits=[
        EditHunk(search="    return 1", replace="    return 10"),
        EditHunk(search="    return 2", replace="    return 20")]))
    assert r["applied"] == 2 and r["written"] and not r["failed"]
    assert "return 10" in (allowed_root() / "proj/app.py").read_text()


async def test_apply_edit_per_hunk_salvage():
    p = _write("proj/b.py", "x = 1\ny = 2\ny = 3\n")
    r = await apply_edit(ApplyEditInput(path="proj/b.py", edits=[
        EditHunk(search="x = 1", replace="x = 100"),          # applies
        EditHunk(search="nope", replace="z"),                  # not found
        EditHunk(search="y = ", replace="y = 0"),              # ambiguous (2 matches)
    ]))
    assert r["applied"] == 1 and r["written"]
    reasons = [f["reason"] for f in r["failed"]]
    assert any("not found" in x for x in reasons) and any("2 times" in x for x in reasons)
    assert "x = 100" in p.read_text() and "y = 2" in p.read_text()  # failed hunks skipped


async def test_apply_edit_all_failed_writes_nothing():
    p = _write("proj/c.py", "a = 1\n")
    r = await apply_edit(ApplyEditInput(path="proj/c.py", edits=[EditHunk(search="zzz", replace="q")]))
    assert r["applied"] == 0 and not r["written"]
    assert p.read_text() == "a = 1\n"


async def test_edit_tools_confined_to_root():
    r = await apply_edit(ApplyEditInput(path="../etc/passwd", edits=[EditHunk(search="x", replace="y")]))
    assert "error" in r
    r = await write_file(WriteFileInput(path="../escape.txt", content="x"))
    assert "error" in r


async def test_write_file_creates_parents():
    r = await write_file(WriteFileInput(path="proj/pkg/new_module.py", content="VALUE = 42\n"))
    assert r["written"] and (allowed_root() / "proj/pkg/new_module.py").read_text() == "VALUE = 42\n"


async def test_repo_map_lists_files_and_signatures():
    _write("mapped/alpha.py", "class A:\n    pass\n\ndef top():\n    pass\n")
    _write("mapped/data.txt", "hello")
    r = await repo_map(RepoMapInput(subdirectory="mapped"))
    assert "alpha.py" in r["map"] and "class A" in r["map"] and "def top" in r["map"]
    assert "data.txt" in r["map"]


async def test_repo_map_budget_truncates():
    for i in range(50):
        _write(f"bigdir/f{i}.py", f"def f{i}():\n    pass\n")
    r = await repo_map(RepoMapInput(subdirectory="bigdir", max_chars=500))
    assert len(r["map"]) <= 600 and "truncated" in r["map"]


async def test_submit_checklist_shape():
    r = await submit(SubmitInput(summary="added feature", files_changed=["a.py"],
                                 verification="pytest: 5 passed"))
    assert r["submitted"] and r["checklist"]["files_changed"] == ["a.py"]


def test_coder_registry_has_coding_tools():
    names = set(worker_registry("coder").names())
    assert {"repo_map", "apply_edit", "write_file", "submit", "read_file"} <= names
    # other workers unchanged
    assert "apply_edit" not in set(worker_registry("researcher").names())
