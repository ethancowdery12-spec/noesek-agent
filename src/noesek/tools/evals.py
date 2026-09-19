"""Promptfoo evaluation integration as a process boundary.

Noesek generates a promptfoo config targeting a local Noesek server endpoint and
runs the pinned promptfoo CLI (promptfoo, MIT) as a subprocess. Noesek owns the
eval definitions, policy, and result parsing; promptfoo owns the runner. No live
accounts: the provider URL must be localhost/127.0.0.1 and any model-grading
provider keys stay in the operator's environment.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yaml


class EvalRunnerError(RuntimeError):
    pass


def build_promptfoo_config(*, endpoint: str, prompts: list[str],
                           cases: list[dict], description: str = "noesek-eval") -> dict:
    """A promptfoo config against a Noesek-compatible HTTP endpoint.

    cases: [{"vars": {...}, "assert": [{"type": "contains", "value": "..."}]}]
    """
    host = urlparse(endpoint)
    if host.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise EvalRunnerError("eval endpoints must be local; live external targets are out of scope")
    return {
        "description": description,
        "prompts": prompts,
        "providers": [{
            "id": "http",
            "config": {
                "url": endpoint,
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body": {"prompt": "{{prompt}}"},
                "transformResponse": "json.text ?? json",
            },
        }],
        "tests": cases,
    }


def write_config(config: dict, directory: str | Path) -> Path:
    path = Path(directory) / "promptfooconfig.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


async def run_eval(config: dict, *, timeout_seconds: float = 600) -> dict:
    """Run promptfoo against the config; returns the parsed JSON results."""
    exe = shutil.which("promptfoo")
    if exe is None:
        npx = shutil.which("npx")
        if npx is None:
            return {"error": "promptfoo is not installed (npm i -g promptfoo) and npx is unavailable"}
        cmd = [npx, "--yes", "promptfoo@latest"]
    else:
        cmd = [exe]
    with tempfile.TemporaryDirectory() as d:
        cfg = write_config(config, d)
        out_path = Path(d) / "results.json"
        cmd += ["eval", "-c", str(cfg), "-o", str(out_path), "--no-progress-bar"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=d)
            _out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            proc.kill(); await proc.wait()
            return {"error": "promptfoo eval timed out"}
        if not out_path.exists():
            return {"error": f"promptfoo produced no results (exit {proc.returncode})",
                    "stderr": err.decode(errors="replace")[-4000:]}
        return json.loads(out_path.read_text())


def build_deepeval_cases(cases: list[dict]) -> list[dict]:
    """deepeval-compatible test-case dicts for a process-isolated runner.

    deepeval (Apache-2.0) is deliberately NOT a Noesek dependency: its import
    graph is heavy. Write these cases to JSON and run deepeval externally:

        deepeval test run  # against a harness that loads this file

    cases: [{"input": str, "expected_output": str?, "context": [str]?}]
    """
    out = []
    for i, c in enumerate(cases):
        if not isinstance(c.get("input"), str) or not c["input"].strip():
            raise EvalRunnerError(f"case {i}: 'input' must be non-empty text")
        case = {"input": c["input"]}
        if c.get("expected_output") is not None:
            case["expected_output"] = c["expected_output"]
        if c.get("context") is not None:
            case["context"] = list(c["context"])
        out.append(case)
    return out
