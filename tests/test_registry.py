import asyncio, json
import pytest
from pydantic import BaseModel
from noesek.core.tools import ToolRegistry, ToolSpec, ToolTimeoutError
from noesek.core.types import Risk

class I(BaseModel): x: int
async def f(i): return {"x": i.x}

async def test_typed_registry_validates():
    r = ToolRegistry(); r.register(ToolSpec("f", "d", I, Risk.READ, f))
    assert (await r.invoke("f", {"x": 3}))["x"] == 3
    with pytest.raises(Exception): await r.invoke("f", {"x": "bad"})

def test_duplicate_registration_rejected():
    r = ToolRegistry(); r.register(ToolSpec("f", "d", I, Risk.READ, f))
    with pytest.raises(ValueError): r.register(ToolSpec("f", "d", I, Risk.READ, f))

async def test_unknown_tool_raises_keyerror():
    r = ToolRegistry()
    with pytest.raises(KeyError): await r.invoke("nope", {})

def test_schemas_are_json_serializable():
    r = ToolRegistry(); r.register(ToolSpec("f", "d", I, Risk.READ, f))
    s = r.schemas(); json.dumps(s)
    assert s[0]["function"]["name"] == "f"
    assert "x" in s[0]["function"]["parameters"]["properties"]

async def test_tool_timeout_enforced():
    async def slow(i): await asyncio.sleep(1); return {}
    r = ToolRegistry(); r.register(ToolSpec("slow", "d", I, Risk.READ, slow, timeout_seconds=0.05))
    with pytest.raises(ToolTimeoutError): await r.invoke("slow", {"x": 1})

def test_invalid_spec_rejected():
    with pytest.raises(ValueError): ToolSpec("bad", "d", I, Risk.READ, f, timeout_seconds=0)
