"""test_verifier: run pytest with coverage over the conversation workspace.

Skills batch 1, item 5 ("pytest+coverage verifier loop"). The verifier half
of the write -> test -> fix loop: the agent writes or changes code in the
code_interpreter workspace, then calls this to get structured results
(pass/fail counts, failed test names, failure output tail, per-file line
coverage) and iterates until green.

Own wiring around pytest (MIT) and coverage (Apache-2.0), both pinned core
deps for this tool. No third-party pytest plugins: results are parsed from
pytest's short summary and coverage's JSON report.

Sandboxing matches code_interpreter (docs/SANDBOX_ISOLATION_DESIGN.md, M1
local backend): scrubbed environment (PATH only - no inherited secrets),
rlimits via the shared interpreter helper, per-call timeout with kill, an
isolated per-conversation workspace as the only writable path, and output
caps. Local backend never disables network (documented limitation).
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

from pydantic import BaseModel, Field

from .interpreter import _limits, _session_root

_MAX_OUTPUT_TAIL = 4000
_MAX_FAILED_LISTED = 25
_MAX_FILES_LISTED = 20

_SUMMARY_RE = re.compile(r"in\s+(?P<secs>[\d.]+)s\s*=*\s*$")
_COUNT_RE = re.compile(r"(\d+)\s+(failed|passed|errors?|skipped|xfailed|xpassed|deselected|warnings)")
_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)


class VerifierInput(BaseModel):
    path: str = Field(default=".", description="Directory with tests, relative to the conversation code workspace (created by code_interpreter). Default: the workspace root.")
    pytest_args: str = Field(default="", max_length=300, description="Extra pytest flags, e.g. '-k login -x'. No file paths - use the path field.")
    coverage: bool = Field(default=True, description="Also compute line coverage (per file + total).")
    timeout_seconds: int = Field(default=120, ge=5, le=300)


def _resolve_target(root: Path, rel: str) -> Path | None:
    try:
        target = (root / rel).resolve()
        target.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return target if target.is_dir() else None


def _parse_pytest_output(text: str) -> dict:
    counts = {"failed": 0, "passed": 0, "errors": 0, "skipped": 0,
              "xfailed": 0, "xpassed": 0, "deselected": 0}
    duration = None
    for line in reversed(text.splitlines()):
        m = _SUMMARY_RE.search(line.strip())
        if m and _COUNT_RE.search(line):
            duration = float(m.group("secs"))
            for n, kind in _COUNT_RE.findall(line):
                key = "errors" if kind.startswith("error") else kind
                if key in counts:
                    counts[key] = int(n)
            break
    failed_tests = _FAILED_RE.findall(text)[:_MAX_FAILED_LISTED]
    return {**counts, "duration_s": duration, "failed_tests": failed_tests}


def _parse_coverage_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    totals = data.get("totals") or {}
    files = []
    for name, info in (data.get("files") or {}).items():
        summary = info.get("summary") or {}
        pct = summary.get("percent_covered")
        if pct is not None:
            files.append({"file": name, "pct": round(float(pct), 1)})
    files.sort(key=lambda f: f["pct"])
    return {
        "total_pct": round(float(totals.get("percent_covered") or 0.0), 1),
        "files": files[:_MAX_FILES_LISTED],
        "files_omitted": max(0, len(files) - _MAX_FILES_LISTED),
    }


async def _run(argv: list[str], cwd: Path, timeout: int) -> tuple[int, str, bool]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd),
        preexec_fn=_limits(timeout) if os.name == "posix" else None,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, out.decode(errors="replace"), False
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", True


async def test_verifier(inp: VerifierInput, conversation_id: int) -> dict:
    if importlib.util.find_spec("pytest") is None:
        return {"ok": False, "error": "pytest is not installed on this host - the verifier is unavailable"}
    rel = inp.path.strip() or "."
    if ".." in rel:
        return {"ok": False, "error": "path must stay inside the conversation workspace"}
    try:
        extra = shlex.split(inp.pytest_args)
    except ValueError as e:
        return {"ok": False, "error": f"could not parse pytest_args: {e}"}
    if any(".." in tok for tok in extra):
        return {"ok": False, "error": "pytest_args must not contain '..'"}
    if any(tok.startswith("--rootdir") or tok.startswith("--confcutdir") for tok in extra):
        return {"ok": False, "error": "rootdir/confcutdir overrides are not allowed"}

    root = _session_root() / str(conversation_id)
    root.mkdir(parents=True, exist_ok=True)
    target = _resolve_target(root, rel)
    if target is None:
        return {"ok": False, "error": f"no such directory in the workspace: {rel}"}

    cov_dir = root / ".verifier_cov"
    cov_dir.mkdir(exist_ok=True)
    for stale in cov_dir.iterdir():
        if stale.is_file():
            stale.unlink()

    use_cov = inp.coverage and importlib.util.find_spec("coverage") is not None
    base = [sys.executable]
    if use_cov:
        base += ["-m", "coverage", "run", f"--data-file={cov_dir / '.coverage'}", "--source=.", "-m"]
    else:
        base += ["-m"]
    argv = base + ["pytest", "-q", "--tb=short", "--color=no", "-p", "no:cacheprovider",
                   f"--rootdir={target}"] + extra + ["."]

    t0 = time.time()
    code, text, timed_out = await _run(argv, target, inp.timeout_seconds)
    if timed_out:
        return {"ok": False, "error": f"test run timed out after {inp.timeout_seconds}s - the process was killed"}
    elapsed = round(time.time() - t0, 2)

    result = _parse_pytest_output(text)
    result["exit_code"] = code
    result["ok"] = code == 0
    if code == 5:
        result["note"] = "no tests collected"
    if not use_cov:
        result["coverage_unavailable"] = inp.coverage
    result["output_tail"] = text[-_MAX_OUTPUT_TAIL:]
    result["output_truncated"] = len(text) > _MAX_OUTPUT_TAIL
    result["elapsed_s"] = elapsed

    if use_cov:
        json_out = cov_dir / "coverage.json"
        code2, _, _ = await _run(
            [sys.executable, "-m", "coverage", "json",
             f"--data-file={cov_dir / '.coverage'}", "-o", str(json_out)],
            target, 30)
        cov = _parse_coverage_json(json_out) if code2 == 0 else None
        if cov is not None:
            result["coverage"] = cov
        else:
            result["coverage_error"] = "coverage report could not be produced (often: no measurable code ran)"
    return result

__test__ = False  # tool module, not a test file (pytest collects src/)
