"""Adapter for upstream evals/toolperf_abeval/ (Hermes c712f06d).

Upstream intent: measure model waste (turns, tool calls, errors, retries,
bytes, wall clock) on a battery of tasks including error-inducing ones.
Narrowed scope: upstream A/B requires paid model runs; this adapter measures
the Noesek orchestration path with a deterministic scripted LLM fixture
(never paid inference), on a three-task battery: plain answer, one tool call,
and an error-inducing unknown-tool task that must recover.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir


class ScriptedLLM:
    """Deterministic fixture: per-task script of (content, tool_calls) replies."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def complete(self, messages, schemas):
        self.calls += 1
        content, tool_calls = self.script.pop(0) if self.script else ("done", [])

        class Reply:
            pass
        r = Reply(); r.content = content; r.tool_calls = tool_calls
        return r


def tool_call(name, arguments):
    class TC:
        pass
    tc = TC(); tc.id = f"call-{name}"; tc.name = name; tc.arguments = arguments
    return tc


BATTERY = {
    "plain": [("final answer", [])],
    "one_tool": [("", [tool_call("run_python", {"code": "print(1)", "timeout_seconds": 5})]),
                 ("tool done", [])],
    "unknown_tool_recovery": [("", [tool_call("no_such_tool", {})]),
                              ("recovered after tool error", [])],
}


async def go():
    from noesek.workers.runner import run_worker
    metrics = {}
    for task, script in BATTERY.items():
        llm = ScriptedLLM(script)
        start = time.monotonic()
        result = await run_worker("operator", f"task: {task}", llm=llm)
        metrics[task] = {
            "llm_turns": llm.calls,
            "wall_ms": round((time.monotonic() - start) * 1000, 1),
            "result_bytes": len(json.dumps(result, default=str).encode()),
            "content": (result.get("output") or "")[:60] if isinstance(result, dict) else str(result)[:60],
            "steps": result.get("steps") if isinstance(result, dict) else None,
        }
    return metrics


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    import os
    os.environ.update({"NOESEK_HOME": str(home), "HERMES_HOME": str(home),
                       "NOESEK_DATABASE_URL": f"sqlite+aiosqlite:///{home}/noesek.db"})
    metrics = asyncio.run(go())
    (out / "orchestration_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    rec = metrics["unknown_tool_recovery"]
    ok = (metrics["plain"]["llm_turns"] == 1 and metrics["one_tool"]["llm_turns"] == 2
          and "recovered" in rec["content"] and rec["llm_turns"] == 2)
    emit("pass" if ok else "fail", metrics=metrics,
         deviation="scripted LLM fixture instead of paid model A/B; measures orchestration, not model quality",
         metrics_path=str(out / "orchestration_metrics.json"))


if __name__ == "__main__":
    main()
