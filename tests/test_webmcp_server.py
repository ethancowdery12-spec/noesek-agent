"""Tests for the WebMCP-style page sidecar (roadmap item 50)."""
import socket
import threading
import time

import pytest
import uvicorn

from noesek.core.webmcp_server import build_app, configured_pages


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Running:
    def __init__(self, app, port):
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("server did not start")

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=5)


PAGE_HTML = """<html><head><title>Demo Page</title></head><body>
<h1>Hello from the fixture</h1><p>Some readable text.</p>
<a href="https://example.com/a">A</a><a href="https://example.com/b">B</a>
</body></html>"""


@pytest.fixture()
def stack(monkeypatch):
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse
    from starlette.routing import Route

    async def page(request):
        return HTMLResponse(PAGE_HTML)

    page_port, mcp_port = _free_port(), _free_port()
    page_app = Starlette(routes=[Route("/", page)])
    monkeypatch.setenv("NOESEK_WEBMCP_PAGES", '{"demo": "http://127.0.0.1:%d/"}' % page_port)
    from noesek.config import settings
    monkeypatch.setattr(settings, "webmcp_pages", '{"demo": "http://127.0.0.1:%d/"}' % page_port)
    with _Running(page_app, page_port), _Running(build_app(), mcp_port):
        yield mcp_port


def test_configured_pages_parsing(monkeypatch):
    assert configured_pages("") == {}
    assert configured_pages("not json") == {}
    assert configured_pages('{"good": "https://x.com", "BAD NAME": "https://x.com", "nohttps": "ftp://x"}') == {"good": "https://x.com"}


async def test_pages_become_mcp_tools(stack):
    from noesek.core.mcp_client import MCPServer, call_tool_text, mcp_session

    server = MCPServer("pages", f"http://127.0.0.1:{stack}/mcp")
    async with mcp_session(server) as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert names == {"page_read", "page_links"}

        out = await call_tool_text(session, "page_read", {"name": "demo"})
        assert "Demo Page" in out and "readable text" in out

        links = await call_tool_text(session, "page_links", {"name": "demo"})
        assert "https://example.com/a" in links and "https://example.com/b" in links

        unknown = await call_tool_text(session, "page_read", {"name": "evil"})
        assert "unknown page" in unknown and "demo" in unknown  # never fetches unconfigured URLs


async def test_fetch_failure_is_clean(stack, monkeypatch):
    from noesek.core.mcp_client import MCPServer, call_tool_text, mcp_session

    monkeypatch.setattr("noesek.core.webmcp_server._fetch", _boom)
    server = MCPServer("pages", f"http://127.0.0.1:{stack}/mcp")
    async with mcp_session(server) as session:
        out = await call_tool_text(session, "page_read", {"name": "demo"})
        assert "fetch failed" in out


async def _boom(url):
    raise ValueError("nope")
