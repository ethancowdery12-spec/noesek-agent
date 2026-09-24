"""code_act: compose read-only tools in one sandboxed Python program.

Skills batch 3, top pick (code-act MIT / smolagents Apache pattern,
own-words implementation - nothing copied). The model acts by writing
Python instead of narrating tool calls one at a time: call_tool(name,
**args) invokes a real registered tool through a JSON-lines RPC bridge to
the host process, results come back as values, and the program loops,
filters, joins, and aggregates before emit()ing a final answer. This
directly targets the observed failure mode of made-up tool results: every
intermediate value comes from a real execution with a returned trace, so
there is nothing for the model to confabulate about - it either called the
tool and got the value, or the value does not exist.

M1 scope: READ-risk tools only (no side effects from sandbox code),
local-subprocess backend with the same sandbox posture as code_interpreter
(docs/SANDBOX_ISOLATION_DESIGN.md): scrubbed env, rlimits, per-call and
overall timeouts with kill, output caps, per-conversation workspace cwd.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .interpreter import _limits, _session_root

_MAX_STDOUT = 4000
_MAX_ARG_BYTES = 20000
_MAX_RESULT_BYTES = 30000
_MAX_TRACE = 20

# The driver: user code runs with stdout redirected to a buffer, so every
# line on the real stdout is protocol. call_tool writes an RPC request and
# blocks on the host's response line; the final line reports completion.
_DRIVER = r"""
import sys, json, traceback, io
_real_out, _real_in = sys.stdout, sys.stdin

def _send(obj):
    _real_out.write(json.dumps(obj) + "\n")
    _real_out.flush()

class ToolError(Exception):
    pass

_rpc_id = 0
def call_tool(name, **kwargs):
    global _rpc_id
    _rpc_id += 1
    _send({"rpc": _rpc_id, "tool": name, "args": kwargs})
    line = _real_in.readline()
    if not line:
        raise ToolError("host closed the bridge")
    resp = json.loads(line)
    if not resp.get("ok"):
        raise ToolError(resp.get("error") or "tool failed")
    return resp.get("result")

_emitted = []
def emit(value):
    _emitted.append(value if isinstance(value, str) else json.dumps(value, default=str))

def _main(code):
    buf = io.StringIO()
    ns = {"__name__": "__main__", "call_tool": call_tool, "emit": emit,
          "ToolError": ToolError, "json": json}
    error = None
    real = sys.stdout
    sys.stdout = buf
    try:
        exec(compile(code, "<codeact>", "exec"), ns)
    except BaseException:
        error = traceback.format_exc(limit=6)
    finally:
        sys.stdout = real
    _send({"done": True, "stdout": buf.getvalue(),
           "emitted": _emitted[-1] if _emitted else None, "error": error})

req = json.loads(_real_in.readline())
_main(req.get("code", ""))
"""


class CodeActInput(BaseModel):
    task: str = Field(min_length=3, max_length=500,
                      description="What this program accomplishes, one sentence")
    code: str = Field(min_length=10, max_length=20000,
                      description="Python program. call_tool(name, **args) invokes a read-only chat tool and returns its real result; emit(value) sets the final answer; print() for working notes. ToolError is raised for unknown/failed tools and can be caught.")
    max_tool_calls: int = Field(default=8, ge=1, le=20)
    timeout_seconds: int = Field(default=60, ge=5, le=180)


def _workspace(conversation_id: int) -> Path:
    d = _session_root() / str(conversation_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _run_codeact(
    inp: CodeActInput,
    conversation_id: int,
    invoke: Callable[[str, dict], Awaitable[Any]],
    allowed: Callable[[], set[str]],
) -> dict:
    import shutil
    python = shutil.which("python3") or shutil.which("python")
    if not python:
        return {"ok": False, "error": "no python interpreter on PATH"}
    proc = await asyncio.create_subprocess_exec(
        python, "-u", "-c", _DRIVER,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=str(_workspace(conversation_id)),
        preexec_fn=_limits(inp.timeout_seconds) if os.name == "posix" else None,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})

    t0 = time.time()
    trace: list[dict] = []
    calls = 0

    async def _readline():
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=inp.timeout_seconds)
        if not line:
            raise ConnectionError("driver exited without completing")
        return json.loads(line.decode())

    async def _write(obj: dict):
        proc.stdin.write(json.dumps(obj).encode() + b"\n")
        await proc.stdin.drain()

    try:
        await _write({"code": inp.code})
        while True:
            msg = await _readline()
            if "done" in msg:
                break
            # RPC request from the sandbox
            rpc_id = msg.get("rpc")
            name = str(msg.get("tool") or "")
            args = msg.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            calls += 1
            t_start = time.time()
            if calls > inp.max_tool_calls:
                await _write({"rpc": rpc_id, "ok": False,
                              "error": f"tool-call budget exceeded ({inp.max_tool_calls})"})
                trace.append({"tool": name, "ok": False, "error": "budget"})
                continue
            if len(json.dumps(args)) > _MAX_ARG_BYTES:
                await _write({"rpc": rpc_id, "ok": False, "error": "arguments too large"})
                trace.append({"tool": name, "ok": False, "error": "args_too_large"})
                continue
            if name not in allowed():
                await _write({"rpc": rpc_id, "ok": False,
                              "error": f"tool {name!r} is not callable from code_act (read-only tools only)"})
                trace.append({"tool": name, "ok": False, "error": "not_allowed"})
                continue
            try:
                result = invoke(name, args)
                if inspect.isawaitable(result):
                    result = await result
                payload = json.dumps(result, default=str)
                if len(payload) > _MAX_RESULT_BYTES:
                    result = payload[:_MAX_RESULT_BYTES] + "...[truncated]"
                await _write({"rpc": rpc_id, "ok": True, "result": result})
                trace.append({"tool": name, "ok": True,
                              "ms": round((time.time() - t_start) * 1000)})
            except Exception as e:  # tool failure must not kill the bridge
                await _write({"rpc": rpc_id, "ok": False, "error": str(e)[:500]})
                trace.append({"tool": name, "ok": False, "error": str(e)[:200]})
    except (TimeoutError, ConnectionError, BrokenPipeError, ConnectionResetError) as e:
        proc.kill()
        await proc.wait()
        reason = ("timed out" if isinstance(e, TimeoutError) else "driver process died")
        return {"ok": False, "error": f"{reason} after {inp.timeout_seconds}s - the process was killed",
                "calls": calls, "trace": trace[-_MAX_TRACE:]}
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except (ProcessLookupError, OSError):
                pass

    out, err = msg.get("stdout") or "", msg.get("error")
    return {
        "ok": err is None,
        "task": inp.task,
        "emitted": (msg.get("emitted") or "")[:4000] or None,
        "stdout_tail": out[-_MAX_STDOUT:],
        "stdout_truncated": len(out) > _MAX_STDOUT,
        "error": err,
        "calls": calls,
        "trace": trace[-_MAX_TRACE:],
        "trace_note": "every tool result in this run came from a real execution listed here",
        "elapsed_s": round(time.time() - t0, 2),
    }


def codeact_handler(
    conversation_id: int,
    invoke: Callable[[str, dict], Awaitable[Any]],
    allowed: Callable[[], set[str]],
):
    async def _handle(inp: CodeActInput) -> dict:
        return await _run_codeact(inp, conversation_id, invoke, allowed)
    return _handle
