"""Item 61: exact_solve tool + local-subprocess fallback + reason_route playbook."""
import os
import shutil

import pytest

from noesek.tools.exact_solve import ExactSolveInput, _parse, exact_solve
from noesek.tools.playbook import PLAYBOOKS
from noesek.tools import sandbox_backends as sb


# --- contract parsing -------------------------------------------------------

def test_parse_verified_and_unsolvable():
    out = _parse("thinking...\nSTATUS: VERIFIED\nANSWER: 42\n")
    assert out == {"status": "VERIFIED", "answer": "42"}
    out = _parse("search exhausted\nANSWER: no solution exists for N=6 with boat=2\nSTATUS: UNSOLVABLE\n")
    assert out["status"] == "UNSOLVABLE" and "no solution" in out["answer"]


def test_parse_rejects_missing_markers():
    assert _parse("the answer is probably 42") is None
    assert _parse("STATUS: VERIFIED\n") is None
    assert _parse("ANSWER: 42\n") is None


# --- tool behavior with a fake backend --------------------------------------

class _FakeBackend:
    def __init__(self, result): self._r = result
    async def run_python(self, code, *, image, timeout_seconds): return self._r


@pytest.mark.asyncio
async def test_exact_solve_verified(monkeypatch):
    monkeypatch.setattr(sb, "get_backend",
                        lambda name=None: _FakeBackend(
                            {"exit_code": 0, "stdout": "moves: 255\nSTATUS: VERIFIED\nANSWER: 255\n",
                             "stderr": "", "backend": "fake"}))
    import noesek.tools.exact_solve as xs
    monkeypatch.setattr(xs, "get_backend", lambda name=None: _FakeBackend(
        {"exit_code": 0, "stdout": "moves: 255\nSTATUS: VERIFIED\nANSWER: 255\n",
         "stderr": "", "backend": "fake"}))
    out = await exact_solve(ExactSolveInput(goal="hanoi 8 disks min moves", code="print(1)  # solver"))
    assert out["status"] == "VERIFIED" and out["answer"] == "255" and out["backend"] == "fake"


@pytest.mark.asyncio
async def test_exact_solve_unsolvable_and_contract_violation(monkeypatch):
    import noesek.tools.exact_solve as xs
    monkeypatch.setattr(xs, "get_backend", lambda name=None: _FakeBackend(
        {"exit_code": 0, "stdout": "bound 6 pairs / boat 2 exhausted\nANSWER: impossible: boat capacity 2 cannot carry 6 pairs\nSTATUS: UNSOLVABLE\n",
         "stderr": "", "backend": "fake"}))
    out = await exact_solve(ExactSolveInput(goal="river crossing N=6", code="print(1)  # solver"))
    assert out["status"] == "UNSOLVABLE" and "prov" in out["note"]
    monkeypatch.setattr(xs, "get_backend", lambda name=None: _FakeBackend(
        {"exit_code": 0, "stdout": "I think it works", "stderr": "", "backend": "fake"}))
    out = await exact_solve(ExactSolveInput(goal="test goal", code="print(1)  # solver"))
    assert "contract violation" in out["error"]


@pytest.mark.asyncio
async def test_exact_solve_executor_down_degrades(monkeypatch):
    import noesek.tools.exact_solve as xs
    monkeypatch.setattr(xs, "get_backend", lambda name=None: _FakeBackend(
        {"error": "Docker is not installed or not runnable on PATH", "backend": "docker-cli"}))
    out = await exact_solve(ExactSolveInput(goal="test goal", code="print(1)  # solver"))
    assert "error" in out and "unverified" in out["note"]


# --- local-subprocess fallback ----------------------------------------------

@pytest.mark.skipif(shutil.which("python3") is None, reason="no python3")
@pytest.mark.asyncio
async def test_local_subprocess_runs_and_strips_env():
    b = sb.LocalSubprocessBackend()
    res = await b.run_python(
        "import os\nprint('KEY_VISIBLE:', bool(os.environ.get('NOESEK_ANTHROPIC_API_KEY')))\n"
        "print('STATUS: VERIFIED')\nprint('ANSWER: ok')",
        image="unused", timeout_seconds=10)
    assert res["exit_code"] == 0 and res["backend"] == "local-subprocess"
    assert "KEY_VISIBLE: False" in res["stdout"] and "STATUS: VERIFIED" in res["stdout"]


@pytest.mark.asyncio
async def test_get_backend_auto_falls_back_without_docker(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: None if x == "docker" else shutil.which.__wrapped__(x) if hasattr(shutil.which, "__wrapped__") else None)
    monkeypatch.setattr(sb.shutil, "which", lambda x: None if x == "docker" else "/usr/bin/python3")
    b = sb.get_backend("docker-cli")
    assert isinstance(b, sb.LocalSubprocessBackend)


# --- playbook ----------------------------------------------------------------

def test_reason_route_playbook_counters():
    brief = PLAYBOOKS["reason_route"]["brief"].lower()
    for marker in ("exact", "exact_solve", "self-verifying", "unsolvable", "feasibility",
                   "overthinking", "directly", "never cut effort"):
        assert marker in brief, f"reason_route brief missing: {marker}"
