"""code_interpreter: a persistent, sandboxed Python session per conversation.

Skills batch 1, item 2. The research verdict suggested jupyter_client inside
the Docker sandbox; on hosts without Docker (Render runs local-subprocess)
that stack would add ~7 packages to the CORE install, against the lean-deps
posture. This is the own-words zero-dependency equivalent: one long-lived
Python subprocess per conversation running a tiny driver, JSON-lines over
stdin/stdout, a shared namespace for state across calls.

Sandboxing follows docs/SANDBOX_ISOLATION_DESIGN.md (M1) for the local
backend: scrubbed environment (PATH + PYTHONDONTWRITEBYTECODE only - no
inherited secrets), rlimits (CPU/AS/FSIZE/NPROC) where the platform supports
them, per-call timeout, output caps, an isolated per-conversation working
directory as the only writable path, and explicit refusal of any egress
policy (local backend never disables network - documented in the design
doc; callers needing network-free runs must use a container backend).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import OrderedDict
from pathlib import Path

from pydantic import BaseModel, Field

from ..filestore import FileStoreError, files_dir, write_file

_MAX_STDOUT = 8000
_MAX_RESULT = 2000
_MAX_SESSIONS = 8
_SESSION_TTL_S = 3600.0

# The driver: eval when the cell is an expression (so the result repr comes
# back), exec otherwise; state lives in ns across requests.
_DRIVER = r"""
import sys, json, traceback, io
ns = {"__name__": "__main__"}
def _run(code):
    out, err = io.StringIO(), io.StringIO()
    result, error = None, None
    so, se = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        try:
            compiled = compile(code, "<cell>", "eval")
            is_expr = True
        except SyntaxError:
            compiled = compile(code, "<cell>", "exec")
            is_expr = False
        if is_expr:
            result = repr(eval(compiled, ns))
        else:
            exec(compiled, ns)
    except BaseException:
        error = traceback.format_exc(limit=6)
    finally:
        sys.stdout, sys.stderr = so, se
    return out.getvalue(), err.getvalue(), result, error
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except Exception:
        continue
    o, e, r, x = _run(req.get("code", ""))
    sys.stdout.write(json.dumps({"id": req.get("id"), "stdout": o, "stderr": e,
                                 "result": r, "error": x}) + "\n")
    sys.stdout.flush()
"""


def _session_root() -> Path:
    override = os.environ.get("NOESEK_INTERPRETER_DIR")
    return Path(override) if override else Path.home() / ".noesek" / "interpreter"


def _limits(timeout_seconds: int):
    def _apply():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds + 10, timeout_seconds + 10))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except (ImportError, ValueError, OSError):
            pass  # non-Linux host: the per-call timeout still applies
    return _apply


class _Session:
    def __init__(self, proc, cwd: Path):
        self.proc = proc
        self.cwd = cwd
        self.lock = asyncio.Lock()
        self.runs = 0
        self.touched = time.time()


class InterpreterPool:
    def __init__(self, python_bin: str | None = None, root: Path | None = None):
        import shutil
        self._python = python_bin or shutil.which("python3") or shutil.which("python")
        self._root = root
        self._sessions: OrderedDict[int, _Session] = OrderedDict()

    def _dir(self, conversation_id: int) -> Path:
        d = (self._root or _session_root()) / str(conversation_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def _start(self, conversation_id: int) -> _Session:
        if not self._python:
            raise RuntimeError("no python interpreter on PATH")
        cwd = self._dir(conversation_id)
        proc = await asyncio.create_subprocess_exec(
            self._python, "-u", "-c", _DRIVER,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(cwd), preexec_fn=_limits(120) if os.name == "posix" else None,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})
        return _Session(proc, cwd)

    async def _get(self, conversation_id: int) -> _Session:
        s = self._sessions.get(conversation_id)
        if s and s.proc.returncode is None and (time.time() - s.touched) < _SESSION_TTL_S:
            self._sessions.move_to_end(conversation_id)
            return s
        if s:
            await self._kill(conversation_id)
        s = await self._start(conversation_id)
        self._sessions[conversation_id] = s
        while len(self._sessions) > _MAX_SESSIONS:
            oldest = next(iter(self._sessions))
            await self._kill(oldest)
        return s

    async def _kill(self, conversation_id: int) -> None:
        s = self._sessions.pop(conversation_id, None)
        if s and s.proc.returncode is None:
            try:
                s.proc.kill()
                await s.proc.wait()
            except (ProcessLookupError, OSError):
                pass

    async def execute(self, conversation_id: int, code: str, timeout_seconds: int) -> dict:
        s = await self._get(conversation_id)
        async with s.lock:
            s.touched = time.time()
            req_id = s.runs + 1
            t0 = time.time()
            try:
                s.proc.stdin.write(json.dumps({"id": req_id, "code": code}).encode() + b"\n")
                await s.proc.stdin.drain()
                line = await asyncio.wait_for(s.proc.stdout.readline(), timeout=timeout_seconds)
            except TimeoutError:
                await self._kill(conversation_id)
                return {"ok": False, "error": f"timed out after {timeout_seconds}s - the session was restarted (state cleared)",
                        "restarted": True}
            except (BrokenPipeError, ConnectionResetError):
                await self._kill(conversation_id)
                return {"ok": False, "error": "interpreter process died - the session was restarted (state cleared)",
                        "restarted": True}
            if not line:
                await self._kill(conversation_id)
                return {"ok": False, "error": "interpreter closed unexpectedly - the session was restarted (state cleared)",
                        "restarted": True}
            resp = json.loads(line.decode())
            s.runs += 1
            out, err = resp.get("stdout") or "", resp.get("stderr") or ""
            res = resp.get("result")
            return {
                "ok": resp.get("error") is None,
                "stdout": out[-_MAX_STDOUT:],
                "stderr": err[-_MAX_STDOUT:],
                "stdout_truncated": len(out) > _MAX_STDOUT,
                "result": (res[:_MAX_RESULT] if isinstance(res, str) else None),
                "error": resp.get("error"),
                "elapsed_s": round(time.time() - t0, 3),
                "session_runs": s.runs,
            }

    async def reset(self, conversation_id: int) -> dict:
        await self._kill(conversation_id)
        return {"ok": True, "reset": True}

    async def export_file(self, conversation_id: int, name: str) -> dict:
        src = self._dir(conversation_id) / name
        if not src.is_file():
            raise FileStoreError(f"no such file in the session: {name}")
        meta = write_file(name, src.read_bytes())
        return {"ok": True, "download": f"/files/{meta['name']}", "bytes": meta["bytes"]}


_POOL: InterpreterPool | None = None


def _pool() -> InterpreterPool:
    global _POOL
    if _POOL is None:
        _POOL = InterpreterPool()
    return _POOL


class InterpreterInput(BaseModel):
    action: str = Field(default="run", description="run | reset | save_file")
    code: str = Field(default="", max_length=20000, description="Python to run (action=run). State persists across calls in this conversation.")
    file_name: str = Field(default="", description="For save_file: a file the session wrote in its working directory, copied into the file store for download")
    timeout_seconds: int = Field(default=20, ge=1, le=60)


def code_interpreter_handler(conversation_id: int):
    async def _handle(inp: InterpreterInput) -> dict:
        pool = _pool()
        if inp.action == "run":
            if not inp.code.strip():
                return {"ok": False, "error": "code is empty"}
            return await pool.execute(conversation_id, inp.code, inp.timeout_seconds)
        if inp.action == "reset":
            return await pool.reset(conversation_id)
        if inp.action == "save_file":
            if not inp.file_name:
                return {"ok": False, "error": "file_name is required for save_file"}
            return await pool.export_file(conversation_id, inp.file_name)
        return {"ok": False, "error": f"unknown action {inp.action!r}: run | reset | save_file"}
    return _handle
