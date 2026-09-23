"""Needle 3 tool router (item 64): stub building, routing, and offline behavior."""
import sys, types
from pydantic import BaseModel, Field
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.tools import needle_router

class _In(BaseModel):
    city: str
    units: str = "metric"
    limit: int = Field(default=5)

def _spec(name="get_weather"):
    async def h(_: BaseModel): return {}
    return ToolSpec(name, "Get weather for a city.", _In, Risk.READ, h)

class _FakeEngine:
    """Simulates needle's real behavior: the engine EXECUTES its tool stubs;
    captured arguments come back through the stubs' recorder."""
    def __init__(self, tools, **kw): self.tools = tools
    def run(self, text):
        self.tools[0](city="Paris")
        return {"type": "respond", "confidence": 0.91, "function_calls": [], "results": [None]}

class _EmptyEngine(_FakeEngine):
    def run(self, text): return {"type": "respond", "function_calls": [], "confidence": 0.2}

def _fake_module(engine_cls=_FakeEngine):
    m = types.ModuleType("needle")
    m.Needle = engine_cls
    return m

def test_stub_matches_input_schema():
    fn = needle_router._stub_for(_spec())
    import inspect
    sig = inspect.signature(fn)
    assert list(sig.parameters) == ["city", "units", "limit"]
    assert sig.parameters["city"].default is inspect.Parameter.empty  # required
    assert sig.parameters["units"].default is None                    # optional
    assert sig.parameters["limit"].annotation is int
    assert fn.__doc__ == "Get weather for a city."

def test_stub_records_captured_arguments():
    rec = []
    fn = needle_router._stub_for(_spec(), rec)
    fn(city="Paris", limit=3)
    assert rec == [("get_weather", {"city": "Paris", "units": None, "limit": 3})]

def test_route_maps_calls_and_confidence(monkeypatch):
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
