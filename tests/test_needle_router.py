"""Needle 3 tool router (item 64/69): stub building, routing, opt-out gating."""
import sys, time, types
from pydantic import BaseModel, Field
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.tools import needle_router

class _In(BaseModel):
    city: str
    units: str = "metric"
    limit: int = Field(default=5)

class _OddOrder(BaseModel):
    """Optional field before a required one - JSON-schema property order like
    this used to produce `def f(a: str = None, b: str):` and silently drop the
    tool (measured: adversarial_review, gmail_send)."""
    note: str = "x"
    city: str
    count: int = 1

def _spec(name="get_weather", model=_In):
    async def h(_: BaseModel): return {}
    return ToolSpec(name, "Get weather for a city.", model, Risk.READ, h)

class _FakeEngine:
    """Simulates needle's real output contract: proposals come back in the
    response's function_calls (the stub recorder sees internal step calls and
    is NOT the proposal source)."""
    last_run_kwargs: dict = {}
    def __init__(self, tools, **kw): self.tools = tools
    def run(self, text, max_steps=8):
        type(self).last_run_kwargs = {"max_steps": max_steps}
        return {"type": "call", "confidence": 0.91,
                "function_calls": [{"name": "get_weather",
                                    "arguments": {"city": "Paris", "units": None}}]}

class _EmptyEngine(_FakeEngine):
    def run(self, text, max_steps=8): return {"type": "respond", "function_calls": [], "confidence": 0.2}

class _SlowEngine(_FakeEngine):
    def run(self, text, max_steps=8): time.sleep(2); return {"type": "respond", "function_calls": [], "confidence": 0.2}

def _fake_module(engine_cls=_FakeEngine):
    m = types.ModuleType("needle")
    m.Needle = engine_cls
    return m

def _drain_run_lock():
    """Wait out any abandoned zombie still holding the process-wide run lock
    (timeout tests leave one on purpose); the lock is global, so tests must
    not leak it into each other."""
    for _ in range(120):
        if needle_router._engine_run_lock.acquire(blocking=False):
            needle_router._engine_run_lock.release()
            return
        time.sleep(0.05)
    raise AssertionError("needle run lock stuck")

def test_stub_all_params_defaulted():
    fn = needle_router._stub_for(_spec())
    import inspect
    sig = inspect.signature(fn)
    assert list(sig.parameters) == ["city", "units", "limit"]
    # every param carries a default so schema property order can never build
    # an invalid signature; required-ness reaches the engine via the schema
    assert all(p.default is None for p in sig.parameters.values())
    assert sig.parameters["limit"].annotation is int
    assert fn.__doc__ == "Get weather for a city."

def test_stub_compiles_when_required_follows_optional():
    fn = needle_router._stub_for(_spec("odd", _OddOrder))
    import inspect
    assert list(inspect.signature(fn).parameters) == ["note", "city", "count"]

def test_stub_records_captured_arguments():
    rec = []
    fn = needle_router._stub_for(_spec(), rec)
    fn(city="Paris", limit=3)
    assert rec == [("get_weather", {"city": "Paris", "units": None, "limit": 3})]

def test_route_uses_engine_function_calls(monkeypatch):
    monkeypatch.setitem(sys.modules, "needle", _fake_module())
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    out = needle_router.route("weather in Paris", [_spec()])
    assert out["calls"] == [{"name": "get_weather", "arguments": {"city": "Paris"}}]  # None defaults stripped
    assert out["confidence"] == 0.91 and out["tools"] == ["get_weather"]

def test_route_returns_none_when_no_tool_fits(monkeypatch):
    monkeypatch.setitem(sys.modules, "needle", _fake_module(_EmptyEngine))
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    assert needle_router.route("tell me a joke", [_spec()]) is None

def test_route_returns_none_when_engine_errors(monkeypatch):
    class Boom:
        def __init__(self, **kw): raise RuntimeError("no model")
    monkeypatch.setitem(sys.modules, "needle", _fake_module(Boom))
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    assert needle_router.route("hi", [_spec()]) is None

def test_route_returns_none_without_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "needle", None)
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    assert needle_router.route("hi", [_spec()]) is None

def test_route_times_out_instead_of_hanging(monkeypatch):
    monkeypatch.setitem(sys.modules, "needle", _fake_module(_SlowEngine))
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    monkeypatch.setenv("NOESEK_NEEDLE_TIMEOUT_SECONDS", "0.1")
    assert needle_router.route("slow query", [_spec()]) is None
    _drain_run_lock()

def test_route_skips_when_engine_busy(monkeypatch):
    """A busy engine (runaway still inside native code) must skip routing,
    never queue or overlap: route() returns None and the turn proceeds
    LLM-only."""
    monkeypatch.setitem(sys.modules, "needle", _fake_module())
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    _drain_run_lock()
    assert needle_router._engine_run_lock.acquire(blocking=False)
    try:
        assert needle_router.route("weather in Paris", [_spec()]) is None
    finally:
        needle_router._engine_run_lock.release()
    # lock free again -> routing works
    out = needle_router.route("weather in Paris", [_spec()])
    assert out["calls"] == [{"name": "get_weather", "arguments": {"city": "Paris"}}]

def test_run_lock_held_until_generation_ends(monkeypatch):
    """The wall-clock guard abandons a slow run, but the lock stays held
    while the native generation is still going - a second route skips, and
    once generation finishes the lock is released for the next one."""
    monkeypatch.setitem(sys.modules, "needle", _fake_module(_SlowEngine))
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    monkeypatch.setenv("NOESEK_NEEDLE_TIMEOUT_SECONDS", "0.1")
    assert needle_router.route("slow query", [_spec()]) is None       # timed out, zombie holds lock
    assert not needle_router._engine_run_lock.acquire(blocking=False)  # zombie still inside run()
    _drain_run_lock()                                                  # zombie finishes, lock released

def test_max_steps_capped_and_env_tunable(monkeypatch):
    monkeypatch.setitem(sys.modules, "needle", _fake_module())
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    monkeypatch.delenv("NOESEK_NEEDLE_MAX_STEPS", raising=False)
    needle_router.route("weather", [_spec()])
    assert _FakeEngine.last_run_kwargs["max_steps"] == 3  # default cap, not the engine's 8
    monkeypatch.setattr(needle_router, "_engine_cache", {})
    monkeypatch.setenv("NOESEK_NEEDLE_MAX_STEPS", "5")
    needle_router.route("weather", [_spec()])
    assert _FakeEngine.last_run_kwargs["max_steps"] == 5

def test_optout_defaults():
    from noesek.config import Settings
    s = Settings()
    assert s.needle_enabled is True          # assist on by default (opt-out)
    assert s.needle_auto_execute is False    # execution off until tuned weights
    assert s.needle_timeout_seconds > 0
