"""code_interpreter: persistent sessions, sandbox posture, file export."""
import os
import sys

import pytest

from noesek.tools.interpreter import (InterpreterInput, InterpreterPool,
                                      code_interpreter_handler)


@pytest.fixture()
async def pool(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("NOESEK_INTERPRETER_DIR", str(tmp_path / "sessions"))
    p = InterpreterPool(python_bin=sys.executable)
    yield p
    for cid in list(p._sessions):
        await p._kill(cid)


async def test_run_returns_stdout_and_result(pool):
    r = await pool.execute(1, "print('hi')", 10)
    assert r["ok"] is True and r["stdout"] == "hi\n"
    r = await pool.execute(1, "6 * 7", 10)
    assert r["result"] == "42"


async def test_state_persists_across_calls(pool):
    await pool.execute(1, "x = 21", 10)
    r = await pool.execute(1, "x * 2", 10)
    assert r["result"] == "42"
    assert r["session_runs"] == 2


async def test_sessions_are_isolated(pool):
    await pool.execute(1, "x = 'one'", 10)
    r = await pool.execute(2, "'x' in dir()", 10)
    assert r["result"] == "False"


async def test_exception_reported_not_fatal(pool):
    r = await pool.execute(1, "1/0", 10)
    assert r["ok"] is False
    assert "ZeroDivisionError" in r["error"]
    r2 = await pool.execute(1, "'still alive'", 10)
    assert r2["result"] == "'still alive'"


async def test_env_is_scrubbed(pool, monkeypatch):
    monkeypatch.setenv("NOESEK_LLM_API_KEY", "sk-sentinel-secret")
    r = await pool.execute(1,
        "import os; print('LEAK' if 'NOESEK_LLM_API_KEY' in os.environ else 'CLEAN')", 10)
    assert r["stdout"].strip() == "CLEAN"


async def test_timeout_restarts_session(pool):
    r = await pool.execute(1, "while True: pass", 1)
    assert r["ok"] is False and r["restarted"] is True
    r2 = await pool.execute(1, "'back'", 10)
    assert r2["result"] == "'back'" and r2["session_runs"] == 1


async def test_reset_clears_state(pool):
    await pool.execute(1, "y = 9", 10)
    await pool.reset(1)
    r = await pool.execute(1, "'y' in dir()", 10)
    assert r["result"] == "False"


async def test_save_file_into_store(pool, tmp_path, monkeypatch):
    await pool.execute(1, "open('data.csv','w').write('a,b\\n1,2\\n')", 10)
    out = await pool.export_file(1, "data.csv")
    assert out["ok"] is True and out["download"] == "/files/data.csv"
    stored = (tmp_path / "store" / "data.csv").read_text()
    assert stored == "a,b\n1,2\n"


async def test_save_missing_file(pool):
    with pytest.raises(Exception, match="no such file"):
        await pool.export_file(1, "nope.csv")


async def test_handler_dispatch(pool, monkeypatch):
    import noesek.tools.interpreter as mod
    monkeypatch.setattr(mod, "_POOL", pool)
    h = code_interpreter_handler(7)
    r = await h(InterpreterInput(action="run", code="1+1"))
    assert r["result"] == "2"
    r = await h(InterpreterInput(action="bogus"))
    assert r["ok"] is False
    r = await h(InterpreterInput(action="run", code="  "))
    assert r["ok"] is False
