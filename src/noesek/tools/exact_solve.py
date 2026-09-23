"""Exact-procedure solving offloaded to code (roadmap item 61).

Grounded in Shojaee et al., "The Illusion of Thinking" (Apple,
arXiv:2506.06941): reasoning models collapse on long exact procedures -
accuracy hits zero past a complexity threshold, effort paradoxically DROPS
near collapse, and models fail to execute even when handed the algorithm.
Lawsen's comment (arXiv:2506.09250) shows exhaustive-move-list output hits
token limits while generating functions succeed, and that some "failures"
were mathematically impossible instances. "Rethinking the Illusion of
Thinking" (arXiv:2507.01231) recovers ground with stepwise/agentic
decomposition but confirms real limits near 8-disk Hanoi.

The get-around, own implementation: never emit long exact traces from the
model's head. The model writes a small solver that COMPUTES and SELF-VERIFIES
the answer (a generating function, in the comment paper's terms); execution
runs in the sandbox backend; only the verified result returns to chat. A
solver that proves infeasibility reports UNSOLVABLE instead of the model
confabulating moves for an impossible instance. Runs through the existing
backend policy surface (docker/docker-py/e2b, or the local-subprocess
fallback on hosts without a container runtime).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .sandbox_backends import get_backend
from ..config import settings


class ExactSolveInput(BaseModel):
    goal: str = Field(min_length=3, max_length=1000,
                      description="The exact question to answer, e.g. 'minimum moves to solve this Tower of Hanoi state with 8 disks'")
    code: str = Field(min_length=10, max_length=20000,
                      description="Python program that COMPUTES the answer and self-verifies it. Must print exactly one 'STATUS: VERIFIED|UNVERIFIED|UNSOLVABLE' line and one 'ANSWER: <answer>' line. When UNSOLVABLE, print a proof or the exhausted-search bound as evidence.")
    timeout_seconds: int = Field(default=20, ge=1, le=30)


_STATUS = ("VERIFIED", "UNVERIFIED", "UNSOLVABLE")


def _parse(stdout: str) -> dict | None:
    ms = re.search(r"^STATUS:\s*(VERIFIED|UNVERIFIED|UNSOLVABLE)\s*$", stdout, re.M)
    ma = re.search(r"^ANSWER:\s*(.+?)\s*$", stdout, re.M | re.S)
    if not ms or not ma:
        return None
    answer = ma.group(1)
    # stop the answer at the STATUS line if it was captured in the .*? span
    answer = re.split(r"^STATUS:", answer, flags=re.M)[0].strip()
    return {"status": ms.group(1), "answer": answer[:2000]}


def _digest(stdout: str) -> str:
    lines = [l for l in stdout.splitlines()
             if l.strip() and not l.startswith(("STATUS:", "ANSWER:"))]
    if not lines:
        return ""
    head = lines[:2] + (["..."] if len(lines) > 4 else []) + lines[-2:]
    return "\n".join(dict.fromkeys(head))[:600]


async def exact_solve(inp: ExactSolveInput) -> dict:
    res = await get_backend().run_python(
        inp.code, image=settings.sandbox_image, timeout_seconds=inp.timeout_seconds)
    if "error" in res:
        return {"error": res["error"], "backend": res.get("backend"),
                "note": "executor unavailable - answer from reasoning instead and say it is unverified"}
    parsed = _parse(res.get("stdout", ""))
    if parsed is None:
        return {"error": "contract violation: solver must print 'STATUS: ...' and 'ANSWER: ...' lines",
                "stdout_tail": (res.get("stdout", "") or "")[-400:],
                "stderr_tail": (res.get("stderr", "") or "")[-400:],
                "backend": res.get("backend")}
    out = {"goal": inp.goal, "status": parsed["status"], "answer": parsed["answer"],
           "backend": res.get("backend"), "digest": _digest(res.get("stdout", ""))}
    if parsed["status"] == "UNVERIFIED":
        out["note"] = "solver produced an answer but its self-check did not pass - treat as a candidate, not a result"
    if parsed["status"] == "UNSOLVABLE":
        out["note"] = "solver proved infeasibility - report that with the evidence instead of proposing moves"
    return out
