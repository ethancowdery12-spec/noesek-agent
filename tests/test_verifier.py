"""Tests for the pytest+coverage verifier loop tool (batch 1 item 5)."""
import os

import pytest

from noesek.tools.test_verifier import VerifierInput
from noesek.tools.test_verifier import test_verifier as _test_verifier

CONV = 4242


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_INTERPRETER_DIR", str(tmp_path))
    d = tmp_path / str(CONV)
    d.mkdir()
    return d


def _write_passing(d):
    (d / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n")
    (d / "test_calc.py").write_text(
        "from calc import add, sub\n\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n\n"
        "def test_sub():\n    assert sub(5, 2) == 3\n")


@pytest.mark.asyncio
async def test_green_run_reports_counts_and_coverage(workspace):
    _write_passing(workspace)
    res = await _test_verifier(VerifierInput(), CONV)
    assert res["ok"] is True
    assert res["passed"] == 2
    assert res["failed"] == 0
    assert res["coverage"]["total_pct"] == 100.0
    files = {f["file"] for f in res["coverage"]["files"]}
    assert "calc.py" in files


@pytest.mark.asyncio
async def test_failing_run_names_the_failed_test(workspace):
    (workspace / "test_bad.py").write_text(
        "def test_broken():\n    assert 1 + 1 == 3\n")
    res = await _test_verifier(VerifierInput(), CONV)
    assert res["ok"] is False
    assert res["failed"] == 1
    assert any("test_broken" in name for name in res["failed_tests"])
    assert "assert" in res["output_tail"]


@pytest.mark.asyncio
async def test_no_tests_collected(workspace):
    res = await _test_verifier(VerifierInput(), CONV)
    assert res["ok"] is False
    assert res["exit_code"] == 5
    assert res["note"] == "no tests collected"


@pytest.mark.asyncio
async def test_path_escape_refused(workspace):
    res = await _test_verifier(VerifierInput(path="../outside"), CONV)
    assert res["ok"] is False
    assert "workspace" in res["error"]
    res = await _test_verifier(VerifierInput(pytest_args="-k ../../etc"), CONV)
    assert res["ok"] is False


@pytest.mark.asyncio
async def test_pytest_args_filter(workspace):
    _write_passing(workspace)
    res = await _test_verifier(VerifierInput(pytest_args="-k test_add"), CONV)
    assert res["ok"] is True
    assert res["passed"] == 1
    assert res["deselected"] == 1


@pytest.mark.asyncio
async def test_timeout_kills_run(workspace):
    (workspace / "test_slow.py").write_text(
        "import time\n\n\ndef test_slow():\n    time.sleep(30)\n")
    res = await _test_verifier(VerifierInput(timeout_seconds=5), CONV)
    assert res["ok"] is False
    assert "timed out" in res["error"]


@pytest.mark.asyncio
async def test_subdir_target(workspace):
    sub = workspace / "pkg"
    sub.mkdir()
    _write_passing(sub)
    res = await _test_verifier(VerifierInput(path="pkg", coverage=False), CONV)
    assert res["ok"] is True
    assert res["passed"] == 2
    assert "coverage" not in res
