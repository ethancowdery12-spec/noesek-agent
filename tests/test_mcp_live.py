"""LIVE Context7 smoke test - manual only. Run: NOESEK_LIVE_CONTEXT7=1 pytest tests/test_mcp_live.py
Exists because the #94 unit tests faked sessions and the real SDK tuple shape shipped broken."""
import os
import pytest
from noesek.core.mcp_client import mcp_servers, mcp_session, call_tool_text, top_library_id

pytestmark = pytest.mark.skipif(os.environ.get("NOESEK_LIVE_CONTEXT7") != "1",
                                reason="live smoke; set NOESEK_LIVE_CONTEXT7=1")

async def test_context7_resolve_and_query_live():
    servers = mcp_servers()
    assert servers and servers[0].name == "context7"
    async with mcp_session(servers[0]) as session:
        resolved = await call_tool_text(session, "resolve-library-id",
                                        {"libraryName": "FastAPI", "query": "lifespan startup"})
        lib = top_library_id(resolved)
        assert lib.startswith("/") and "fastapi" in lib.lower()
        docs = await call_tool_text(session, "query-docs", {"libraryId": lib, "query": "lifespan startup shutdown"})
        assert "lifespan" in docs.lower()
