"""Needle 3 on-device tool router (opt-in; roadmap item 64).

Uses Cactus Compute's Needle 3 engine (Apache-2.0) to pick tools and fill
arguments locally, before the LLM runs. Measured behavior of the engine: it
proposes typed, grammar-constrained calls (arguments always parse), executes
its function stubs internally, and returns an empty call set when nothing in
the toolset fits - off-topic input stays clean.

Routing per the vendor's confidence guidance (act / confirm / refuse):
  - captured calls at or above NOESEK_NEEDLE_MIN_CONFIDENCE -> the controller
    executes them through the SAME policy / approval / audit path as LLM tool
    calls (never bypassed)
  - captured calls below the threshold -> their schemas are activated for the
    LLM turn (deferral assist); the LLM still decides (this is the common
    case on the base model, where correct calls score ~0.3-0.5)
  - no calls captured -> the turn is unchanged
Note: the response-level confidence scores the finished response on the base
weights; per the vendor it becomes product-tunable with tuned weights
(weights=), where routing thresholds should be measured on needle.environments
before lowering them.
Off by default: NOESEK_NEEDLE_ENABLED=1. Needle's anonymous usage telemetry
is disabled via NEEDLE_TELEMETRY=0 before the engine loads.
"""
import os
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
        params.append(f"{pname}: {ptype.__name__}" + ("" if pname in required else " = None"))
    src = (f"def {spec.name}({', '.join(params)}):\n"
           f"    _record.append(({spec.name!r}, dict(locals())))\n"
           f"    return None\n")
    exec(compile(src, f"<needle-stub:{spec.name}>", "exec"), ns)
    fn = ns[spec.name]
    fn.__doc__ = spec.description
    return fn


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
        response = engine.run(text)
    except Exception:
        return None
    finally:
        _current_recorder = []
    calls = [{"name": name, "arguments": {k: v for k, v in args.items() if v is not None}}
             for name, args in recorder if isinstance(args, dict)]
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
