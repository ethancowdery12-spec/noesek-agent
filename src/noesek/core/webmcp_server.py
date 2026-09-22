"""WebMCP-style page sidecar (roadmap item 50): selected web pages as MCP tools.

WebMCP's idea (jasonjmcghee/WebMCP, MIT; now a W3C community proposal) is that
a web page can be an MCP server. This sidecar hosts that pattern for Noesek:
pages named in NOESEK_WEBMCP_PAGES (JSON {"name": "url"}) become MCP tools on a
small Streamable HTTP server (`noesek-webmcp`, default 127.0.0.1:8795). Point
NOESEK_MCP_EXTRA_SERVERS at it ({"webpages": {"url": "http://127.0.0.1:8795/mcp"}})
and the existing MCP client makes the pages callable from chat.

Bounded by construction: only the pre-configured URLs are ever fetched (no
arbitrary-URL proxying), output is capped, and fetch reuses the standard
noesek text extractor (zero added dependencies - the mcp SDK is already pinned).
The webmcp.js browser-widget handshake is a separate follow-up; it is not W3C
compliant and no site Ethan uses today speaks it.
"""
from __future__ import annotations

import json
import re

import httpx

from ..config import settings
from ..tools.web import extract_text

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_READ_CAP = 6000
_LINK_CAP = 50


def configured_pages(raw: str | None = None) -> dict[str, str]:
    """Parse NOESEK_WEBMCP_PAGES: {"name": "https://..."}. Bad entries are dropped."""
    text = (raw if raw is not None else settings.webmcp_pages).strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    out: dict[str, str] = {}
    for name, url in (data or {}).items():
        name, url = str(name).strip().lower(), str(url).strip()
        if _NAME_RE.match(name) and url.lower().startswith(("http://", "https://")):
            out[name] = url
    return out


async def _fetch(url: str) -> tuple[str, str, list[str]]:
    """Fetch one configured page. Returns (title, text, links). Raises on HTTP error."""
    headers = {"User-Agent": "noesek-webmcp/0.1 (+page sidecar)", "Accept": "text/html,text/plain,*/*"}
    async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds,
                                 follow_redirects=True, max_redirects=5) as c:
        r = await c.get(url, headers=headers)
        r.raise_for_status()
        body = r.text
    title, text = extract_text(body) if "html" in r.headers.get("content-type", "") else ("", body)
    links = re.findall(r'href="(https?://[^"]+)"', body)[:_LINK_CAP] if "html" in r.headers.get("content-type", "") else []
    return title, text[:_READ_CAP], links


def build_server():
    """One MCPServer exposing two tools over the configured page set."""
    from mcp.server.mcpserver import MCPServer

    pages = configured_pages()
    server = MCPServer("noesek-webmcp")
    known = ", ".join(sorted(pages)) or "(none configured)"

    @server.tool(description=f"Read a configured web page as clean text. Known pages: {known}")
    async def page_read(name: str) -> str:
        url = pages.get(name.strip().lower())
        if not url:
            return f"unknown page '{name}'. Known pages: {known}"
        try:
            title, text, _ = await _fetch(url)
        except (httpx.HTTPError, ValueError) as e:
            return f"fetch failed: {type(e).__name__}: {str(e)[:200]}"
        return f"# {title or name}\n{text}" if text else f"(no readable text at {url})"

    @server.tool(description=f"List outbound links on a configured web page. Known pages: {known}")
    async def page_links(name: str) -> str:
        url = pages.get(name.strip().lower())
        if not url:
            return f"unknown page '{name}'. Known pages: {known}"
        try:
            _, _, links = await _fetch(url)
        except (httpx.HTTPError, ValueError) as e:
            return f"fetch failed: {type(e).__name__}: {str(e)[:200]}"
        return "\n".join(links) if links else "(no links found)"

    return server


def build_app():
    return build_server().streamable_http_app()


def main() -> None:
    import uvicorn

    uvicorn.run(build_app(), host=settings.webmcp_host, port=settings.webmcp_port)


if __name__ == "__main__":
    main()
