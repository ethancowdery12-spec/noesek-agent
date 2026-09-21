"""MCP client core + Context7 tool (roadmap item 12, Ethan's call Sep 21).

Sessions are faked - no network. The real transport is the MCP SDK over
Streamable HTTP, exercised only by hand against the live Context7 endpoint.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from noesek.config import settings
from noesek.core.mcp_client import call_tool_text, mcp_servers, top_library_id
from noesek.tools.state import LibraryDocsInput, library_docs_handler


class FakeSession:
    def __init__(self, responses):
        self.responses = responses  # tool name -> text (str) or Exception
        self.calls = []

    async def initialize(self):
        return SimpleNamespace(serverInfo=SimpleNamespace(name="fake"))

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        r = self.responses[name]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(isError=False, content=[SimpleNamespace(text=t) for t in r])


def fake_mcp_session(monkeypatch, fake):
    @asynccontextmanager
    async def _session(server):
        yield fake
    import noesek.core.mcp_client as mc
    monkeypatch.setattr(mc, "mcp_session", _session)
    # state.py imports mcp_session lazily from mcp_client, so patching the module attr works


RESOLVE_TEXT = """Here are the top matches:
- Context7-compatible library ID: /vercel/next.js
  Title: Next.js
  Description: The React framework
- Context7-compatible library ID: /facebook/react
  Title: React"""


def test_servers_default_includes_context7(monkeypatch):
    monkeypatch.setattr(settings, "mcp_context7_enabled", True)
    monkeypatch.setattr(settings, "mcp_extra_servers", "")
    ss = mcp_servers()
    assert ss[0].name == "context7" and ss[0].url == "https://mcp.context7.com/mcp"
    assert ss[0].headers() == {}


def test_servers_api_key_sets_bearer(monkeypatch):
    monkeypatch.setattr(settings, "context7_api_key", "k123")
    assert mcp_servers()[0].headers() == {"Authorization": "Bearer k123"}


def test_servers_extra_json(monkeypatch):
    monkeypatch.setattr(settings, "mcp_extra_servers", '{"acme": {"url": "https://mcp.acme.test/mcp", "api_key": "x"}}')
    names = [s.name for s in mcp_servers()]
    assert names == ["context7", "acme"]


def test_servers_bad_json_keeps_builtin(monkeypatch):
    monkeypatch.setattr(settings, "mcp_extra_servers", "{nope")
    assert [s.name for s in mcp_servers()] == ["context7"]


def test_servers_all_disabled(monkeypatch):
    monkeypatch.setattr(settings, "mcp_context7_enabled", False)
    monkeypatch.setattr(settings, "mcp_extra_servers", "")
    assert mcp_servers() == []


def test_top_library_id():
    assert top_library_id(RESOLVE_TEXT) == "/vercel/next.js"
    assert top_library_id("nothing found") == ""


async def test_call_tool_text_joins_blocks():
    s = FakeSession({"t": ["part one", "part two"]})
    assert await call_tool_text(s, "t", {}) == "part one\npart two"


async def test_call_tool_text_raises_on_error():
    class ErrSession:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=True, content=[SimpleNamespace(text="boom")])
    with pytest.raises(RuntimeError, match="boom"):
        await call_tool_text(ErrSession(), "t", {})


async def test_library_docs_happy_path(monkeypatch):
    monkeypatch.setattr(settings, "mcp_context7_enabled", True)
    monkeypatch.setattr(settings, "mcp_extra_servers", "")
    fake = FakeSession({"resolve-library-id": [RESOLVE_TEXT], "query-docs": ["App Router docs: use server components ..."]})
    fake_mcp_session(monkeypatch, fake)
    r = await library_docs_handler()(LibraryDocsInput(library="next.js", question="server components"))
    assert r["library_id"] == "/vercel/next.js" and "server components" in r["docs"]
    assert fake.calls[1] == ("query-docs", {"libraryId": "/vercel/next.js", "query": "server components"})


async def test_library_docs_no_match(monkeypatch):
    fake = FakeSession({"resolve-library-id": ["No libraries matched your query."]})
    fake_mcp_session(monkeypatch, fake)
    r = await library_docs_handler()(LibraryDocsInput(library="not-a-lib", question="anything"))
    assert "error" in r and "candidates" in r


async def test_library_docs_truncates(monkeypatch):
    fake = FakeSession({"resolve-library-id": [RESOLVE_TEXT], "query-docs": ["x" * 9000]})
    fake_mcp_session(monkeypatch, fake)
    r = await library_docs_handler()(LibraryDocsInput(library="next.js", question="q", max_chars=500))
    assert len(r["docs"]) == 500


async def test_library_docs_no_servers(monkeypatch):
    monkeypatch.setattr(settings, "mcp_context7_enabled", False)
    monkeypatch.setattr(settings, "mcp_extra_servers", "")
    r = await library_docs_handler()(LibraryDocsInput(library="next.js", question="q"))
    assert "no MCP servers" in r["error"]


async def test_library_docs_transport_failure_is_clean_error(monkeypatch):
    fake = FakeSession({"resolve-library-id": ConnectionError("dns fail")})
    fake_mcp_session(monkeypatch, fake)
    r = await library_docs_handler()(LibraryDocsInput(library="next.js", question="q"))
    assert r["error"].startswith("Context7 request failed: ConnectionError")


def test_controller_registers_library_docs():
    from noesek.core.controller import Controller
    from noesek.testing import ScriptedLLM
    c = Controller(llm=ScriptedLLM([]))
    reg = c.registry(1)
    assert "library_docs" in reg._tools
