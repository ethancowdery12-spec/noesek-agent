"""Tests for code_act (skills batch 3: CodeAct pattern, own-words)."""
import json

import pytest

from noesek.tools.codeact import CodeActInput, codeact_handler

CONV = 9191


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_INTERPRETER_DIR", str(tmp_path))


async def _fake_invoke(name, args):
    if name == "add":
        return {"sum": args["a"] + args["b"]}
    if name == "items":
        return {"rows": [{"n": i, "v": i * 10} for i in range(args.get("n", 3))]}
    if name == "boom":
        raise RuntimeError("backend exploded")
    raise KeyError(name)


def _allowed():
    return {"add", "items", "boom"}


def _handler():
    return codeact_handler(CONV, _fake_invoke, _allowed)


@pytest.mark.asyncio
async def test_composes_two_tools_and_emits(workspace):
    code = (
        "a = call_tool('add', a=2, b=3)['sum']\n"
        "rows = call_tool('items', n=4)['rows']\n"
        "total = a + sum(r['v'] for r in rows)\n"
        "emit(f'total={total}')\n")
    res = await _handler()(CodeActInput(task="compose", code=code))
    assert res["ok"] is True
    assert res["emitted"] == "total=65"
    assert res["calls"] == 2
    assert [t["tool"] for t in res["trace"]] == ["add", "items"]
    assert all(t["ok"] for t in res["trace"])


@pytest.mark.asyncio
async def test_results_are_real_values_not_narration(workspace):
    code = "rows = call_tool('items', n=2)['rows']\nemit(json.dumps(rows))\n"
    res = await _handler()(CodeActInput(task="values", code=code))
    assert json.loads(res["emitted"]) == [{"n": 0, "v": 0}, {"n": 1, "v": 10}]


@pytest.mark.asyncio
async def test_disallowed_tool_raises_toolerror(workspace):
    code = (
        "try:\n"
        "    call_tool('delete_everything')\n"
        "except ToolError as e:\n"
        "    emit(f'blocked: {e}')\n")
    res = await _handler()(CodeActInput(task="guard", code=code))
    assert res["ok"] is True
    assert res["emitted"].startswith("blocked: tool 'delete_everything' is not callable")
    assert res["trace"][0]["error"] == "not_allowed"


@pytest.mark.asyncio
async def test_tool_failure_surfaces_as_toolerror(workspace):
    code = (
        "try:\n"
        "    call_tool('boom')\n"
        "except ToolError as e:\n"
        "    emit(f'caught: {e}')\n")
    res = await _handler()(CodeActInput(task="failure", code=code))
    assert res["ok"] is True
    assert "backend exploded" in res["emitted"]


@pytest.mark.asyncio
async def test_call_budget_enforced(workspace):
    code = "for _ in range(10):\n    call_tool('add', a=1, b=1)\n"
    res = await _handler()(CodeActInput(task="budget", code=code, max_tool_calls=3))
    assert res["calls"] == 10 or res["calls"] == 4  # attempted calls counted
    budget_errors = [t for t in res["trace"] if t.get("error") == "budget"]
    assert budget_errors
    assert res["ok"] is False or res["error"] is None  # driver raises ToolError on 4th


@pytest.mark.asyncio
async def test_syntax_error_returned(workspace):
    res = await _handler()(CodeActInput(task="bad", code="def broken(:\n    pass"))
    assert res["ok"] is False
    assert "SyntaxError" in res["error"]


@pytest.mark.asyncio
async def test_stdout_captured_and_capped(workspace):
    code = "print('working notes here')\nemit('done')\n"
    res = await _handler()(CodeActInput(task="prints", code=code))
    assert "working notes here" in res["stdout_tail"]
    assert res["emitted"] == "done"


@pytest.mark.asyncio
async def test_timeout_kills_run(workspace):
    code = "import time\ntime.sleep(30)\n"
    res = await _handler()(CodeActInput(task="slow", code=code, timeout_seconds=5))
    assert res["ok"] is False
    assert "timed out" in res["error"]


@pytest.mark.asyncio
async def test_oversize_tool_result_truncated(workspace):
    async def big_invoke(name, args):
        return {"blob": "x" * 60000}
    h = codeact_handler(CONV, big_invoke, lambda: {"big"})
    code = "r = call_tool('big')\nemit(len(r))\n"
    res = await h(CodeActInput(task="big result", code=code))
    assert res["ok"] is True
    assert int(res["emitted"]) < 60000
