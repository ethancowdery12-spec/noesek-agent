"""Minimal MCP client (roadmap item 12, Ethan's call Sep 21).

JSON-RPC over Streamable HTTP through the official MCP SDK (mcp, already a
pinned dependency for the vendored gateway - no new deps). Context7
(https://mcp.context7.com/mcp, MIT server) is the first integrated server:
resolve-library-id -> query-docs for current, version-specific library docs.

Provider-extensible: extra servers come from NOESEK_MCP_EXTRA_SERVERS as JSON
{"name": {"url": "...", "api_key": "..."}}. Sessions are short-lived per
operation; Context7 runs stateless (no MCP-Session-Id), so this is safe.
"""
import json
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx

from ..config import settings


@dataclass(frozen=True)
class MCPServer:
    name: str
    url: str
    api_key: str = ""
    extra: dict = field(default_factory=dict)

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}


def mcp_servers() -> list[MCPServer]:
    """Configured MCP servers. Context7 first (free endpoint, no key needed)."""
    out: list[MCPServer] = []
    if settings.mcp_context7_enabled:
        out.append(MCPServer("context7", settings.mcp_context7_url, settings.context7_api_key))
    raw = (settings.mcp_extra_servers or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            for name, cfg in (data or {}).items():
                if isinstance(cfg, dict) and cfg.get("url"):
                    out.append(MCPServer(str(name), str(cfg["url"]), str(cfg.get("api_key") or "")))
        except (ValueError, AttributeError):
            pass  # bad JSON: keep the built-in servers only
    return out


@asynccontextmanager
async def mcp_session(server: MCPServer):
    """One initialized MCP session over Streamable HTTP; closed on exit."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(headers=server.headers(), timeout=settings.fetch_timeout_seconds) as client:
        async with streamable_http_client(server.url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def call_tool_text(session, name: str, arguments: dict) -> str:
    """Call one MCP tool and join its text content blocks. Raises on tool error."""
    result = await session.call_tool(name, arguments)
    if getattr(result, "isError", False):
        blocks = [getattr(c, "text", "") for c in (result.content or [])]
        raise RuntimeError(f"MCP tool {name} failed: {' '.join(b for b in blocks if b)[:300]}")
    return "\n".join(c.text for c in (result.content or []) if getattr(c, "text", None))


_LIB_ID_RE = re.compile(r"(/[\w.~-]+/[\w.~-]+)")


def top_library_id(resolve_text: str) -> str:
    """First Context7-compatible library id (/org/project) in a resolve result."""
    m = _LIB_ID_RE.search(resolve_text or "")
    return m.group(1) if m else ""
