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
    def __init__(self, tools, **kw): self.tools = tools
    def run(self, text):
        return {"type": "call", "confidence": 0.91,
                "function_calls": [{"name": "get_weather",
                                    "arguments": {"city": "Paris", "units": None}}]}

class _EmptyEngine(_FakeEngine):
    def run(self, text): return {"type": "respond", "function_calls": [], "confidence": 0.2}

class _SlowEngine(_FakeEngine):
    def run(self, text): time.sleep(2); return {"type": "respond", "function_calls": [], "confidence": 0.2}

def _fake_module(engine_cls=_FakeEngine):
    m = types.ModuleType("needle")
    m.Needle = engine_cls
    return m

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

def test_optout_defaults():
    from noesek.config import Settings
    s = Settings()
    assert s.needle_enabled is True          # assist on by default (opt-out)
    assert s.needle_auto_execute is False    # execution off until tuned weights
    assert s.needle_timeout_seconds > 0
