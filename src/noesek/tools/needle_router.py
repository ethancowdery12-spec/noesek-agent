"""Needle 3 on-device tool router (opt-out assist; roadmap item 64/69).

Uses Cactus Compute's Needle 3 engine (Apache-2.0) to pick tools and fill
arguments locally, before the LLM runs. Measured behavior of the engine: it
proposes typed, grammar-constrained calls (arguments always parse), executes
its function stubs internally, and returns an empty call set when nothing in
the toolset fits - off-topic input stays clean.

Routing per the vendor's confidence guidance (act / confirm / refuse):
  - proposed calls always have their schemas activated for the LLM turn
    (deferral assist - the LLM still decides; this is the default behavior)
  - with NOESEK_NEEDLE_AUTO_EXECUTE=1, proposals at or above
    NOESEK_NEEDLE_MIN_CONFIDENCE execute through the SAME policy / approval /
    audit path as LLM tool calls (never bypassed). Auto-execute is off by
    default: measured on the 34-tool production set with base weights, wrong
    picks carried 0.69-0.99 confidence and varied run to run, so no safe
    threshold exists until weights are tuned (vendor: measure thresholds on
    needle.environments with tuned weights=).
  - no calls proposed -> the turn is unchanged
Note: the response-level confidence scores the finished response on the base
weights; per the vendor it becomes product-tunable with tuned weights
(weights=), where routing thresholds should be measured on needle.environments
before lowering them.
One engine.run at a time, process-wide: a busy engine (including a runaway
the guard abandoned) makes route() return None so the turn proceeds LLM-only.
Runaway length is capped via NOESEK_NEEDLE_MAX_STEPS (default 3; the engine
default of 8 measured multi-minute generations on base weights).
On by default (opt-out): NOESEK_NEEDLE_ENABLED=0 disables. Needle's
anonymous usage telemetry is disabled via NEEDLE_TELEMETRY=0 before the
engine loads.
"""
import os
import threading
from ..core.tools import ToolSpec

_JSON_TYPE_TO_PY = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}
_current_recorder: list = []
_engine_cache: dict = {}


def _needle_module():
    os.environ["NEEDLE_TELEMETRY"] = "0"
    import needle  # type: ignore
    return needle


def _stub_for(spec: ToolSpec, recorder=None):
    """Synthesize one annotated python function per ToolSpec so needle's
    constrained decoding matches the tool's real input schema. The stub is
    side-effect-free: it records its captured arguments and returns None."""
    sink = recorder if recorder is not None else _current_recorder
    schema = spec.input_model.model_json_schema()
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    ns: dict = {"_record": sink}
    params = []
    for pname, pdef in props.items():
        ptype = _JSON_TYPE_TO_PY.get((pdef or {}).get("type", "string"), str)
        ns[ptype.__name__] = ptype
        # Every stub param gets a default: JSON-schema property order can place
        # a required param after an optional one, and a bare required param
        # there is a SyntaxError that silently dropped the whole tool (measured:
        # adversarial_review, gmail_send). Required-ness still reaches the
        # engine through the schema/docstring, not the stub signature.
        params.append(f"{pname}: {ptype.__name__} = None")
    src = (f"def {spec.name}({', '.join(params)}):\n"
           f"    _record.append(({spec.name!r}, dict(locals())))\n"
           f"    return None\n")
    exec(compile(src, f"<needle-stub:{spec.name}>", "exec"), ns)
    fn = ns[spec.name]
    fn.__doc__ = spec.description
    return fn


class _EngineBusy(RuntimeError):
    """Another engine.run is still inside the native engine (possibly a
    runaway abandoned by the wall-clock guard). The engine is native code
    over shared buffers, so a concurrent run on the same engine is never
    safe - the turn skips proposals instead of entering or queueing."""


# Held by the engine.run thread itself, from start until generation actually
# ends. Never wait on it: a waiter would hang its request for as long as a
# runaway generation runs (minutes on a shared CPU).
_engine_run_lock = threading.Lock()


def _run_engine(engine, text, timeout_s: float, max_steps: int):
    """Wall-clock guard around ONE engine.run at a time.

    On base weights some inputs send the engine's agent loop into
    multi-minute generations (measured: a calendar query looped 4+ min at
    the 8-step default), so max_steps is capped low and a stuck call is
    abandoned in its daemon thread and treated as no proposal. The abandoned
    thread keeps the run lock until generation actually ends: measured on
    the live shared-CPU box, repeated requests piled overlapping native
    generations onto one engine, starving every other request (and one
    unlucky interleave away from corrupting the native buffers). If a
    generation ever wedges for good, routing stays skipped but chat keeps
    working - degraded assist, never a hung turn."""
    if not _engine_run_lock.acquire(blocking=False):
        raise _EngineBusy("needle engine busy")
    box: dict = {}
    def work():
        try: box["r"] = engine.run(text, max_steps=max_steps)
        except Exception as e: box["e"] = e
        finally: _engine_run_lock.release()
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise TimeoutError(f"needle engine.run exceeded {timeout_s:.0f}s")
    if "e" in box:
        raise box["e"]
    return box.get("r")


def route(text: str, specs: list[ToolSpec]) -> dict | None:
    """Run needle over the given tool specs. Returns None when the engine is
    unavailable, errors, or finds no fitting tools; otherwise
    {"calls": [{"name","arguments"}], "confidence": float, "tools": [names]}."""
    global _current_recorder
    recorder: list = []
    _current_recorder = recorder
    stubs = []
    for spec in specs:
        try:
            stubs.append(_stub_for(spec, recorder))
        except Exception:
            continue
    if not stubs:
        return None
    key = tuple(s.__name__ for s in stubs)
    try:
        needle = _needle_module()
        engine = _engine_cache.get("engine")
        if _engine_cache.get("key") != key:
            engine = needle.Needle(tools=stubs)
            _engine_cache.clear()
            _engine_cache.update({"engine": engine, "key": key, "stubs": stubs})
        timeout_s = float(os.environ.get("NOESEK_NEEDLE_TIMEOUT_SECONDS", "20"))
        max_steps = int(os.environ.get("NOESEK_NEEDLE_MAX_STEPS", "3"))
        response = _run_engine(engine, text, timeout_s, max_steps)
    except Exception:
        return None
    finally:
        _current_recorder = []
    # The engine's own final proposal is response["function_calls"]; the stub
    # recorder instead catches INTERNAL step calls (the engine executing stubs
    # mid-loop) and misses the final ones - measured: a memory question
    # "captured" list_tasks while the engine's real proposal was empty.
    calls = []
    if isinstance(response, dict):
        for fc in response.get("function_calls") or []:
            if not isinstance(fc, dict) or not fc.get("name"):
                continue
            args = fc.get("arguments") or {}
            calls.append({"name": fc["name"],
                          "arguments": {k: v for k, v in args.items() if v is not None}})
    if not calls:
        return None
    conf = 0.0
    if isinstance(response, dict) and response.get("confidence") is not None:
        try:
            conf = float(response["confidence"])
        except (TypeError, ValueError):
            conf = 0.0
    return {"calls": calls, "confidence": conf,
            "tools": sorted({c["name"] for c in calls})}
