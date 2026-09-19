"""Stage F: deferred schema exposure (search-then-activate) + MCP policy routing."""
from pydantic import BaseModel

from noesek.core.controller import Controller
from noesek.core.tools import ToolRegistry, ToolSpec
from noesek.core.types import Risk
from noesek.db import Conversation, Session
from noesek.testing import ScriptedLLM, tool_reply, text_reply


class Q(BaseModel): q: str = "x"


async def _conv(uid="u1"):
    async with Session() as s:
        c = Conversation(channel="cli", external_user_id=uid); s.add(c); await s.commit(); return c.id


def _registry_with(n_tools):
    def factory(cid):
        r = ToolRegistry()
        for i in range(n_tools):
            async def h(inp): return {"ok": True}
            r.register(ToolSpec(f"tool_{i}", f"does thing {i}", Q, Risk.READ, h))
        return r
    return factory


def test_defer_hides_schemas_until_activated():
    r = ToolRegistry()
    async def h(inp): return {}
    r.register(ToolSpec("alpha", "first tool", Q, Risk.READ, h))
    r.register(ToolSpec("beta", "second tool", Q, Risk.READ, h))
    r.defer("beta")
    names = [s["function"]["name"] for s in r.schemas()]
    assert names == ["alpha"] and r.deferred_names() == ["beta"]
    assert "beta" in r.search("second")  # still searchable
    r.activate("beta")
    assert len(r.schemas()) == 2 and r.deferred_names() == []


async def test_search_tools_activates_deferred(db, monkeypatch):
    from noesek.config import settings
    monkeypatch.setattr(settings, "tool_defer_threshold", 3)
    cid = await _conv()
    llm = ScriptedLLM([tool_reply("search_tools", {"query": "thing 4"}, call_id="c1"),
                       text_reply("done")])
    c = Controller(llm=llm, registry_factory=_registry_with(6))
    r = await c.handle(cid, "find a tool")
    assert r.text == "done"
    second = llm.requests[1]
    offered = [t["function"]["name"] for t in second["tools"]]
    assert "tool_4" in offered  # activated after search
    assert "search_tools" in offered


async def test_deferral_off_by_default(db):
    cid = await _conv()
    llm = ScriptedLLM([text_reply("hi")])
    c = Controller(llm=llm, registry_factory=_registry_with(30))
    await c.handle(cid, "hi")
    offered = [t["function"]["name"] for t in llm.requests[0]["tools"]]
    assert "tool_29" in offered and "search_tools" not in offered


def test_mcp_tool_spec_defaults_to_external_risk():
    from noesek.compat.mcp_real import mcp_tool_spec
    class FakeServer: name = "srv"
    class FakeClient:
        server = FakeServer()
        async def call_tool(self, name, arguments): return []
    spec = mcp_tool_spec(FakeClient(), "read_issue", "fetch an issue")
    assert spec.name == "mcp_read_issue" and spec.risk == Risk.EXTERNAL


async def test_mcp_tool_gated_by_policy_engine(db):
    """An MCP tool (EXTERNAL risk) must pause for approval like any external tool."""
    from noesek.compat.mcp_real import mcp_tool_spec
    class FakeServer: name = "srv"
    class FakeClient:
        server = FakeServer()
        async def call_tool(self, name, arguments): return ["ok"]
    def factory(cid):
        r = ToolRegistry(); r.register(mcp_tool_spec(FakeClient(), "read_issue")); return r
    cid = await _conv()
    c = Controller(llm=ScriptedLLM([tool_reply("mcp_read_issue", {"arguments": {"n": 1}})]),
                   registry_factory=factory)
    r = await c.handle(cid, "read issue 1")
    assert r.pending_approval_id is not None
