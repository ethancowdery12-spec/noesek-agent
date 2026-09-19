"""Real MCP client backend over the pinned official MCP Python SDK.

Noesek's compat.mcp ExternalServer policy stays the outer gate: a server must
be enabled, transport-supported, and carry an explicit tool allowlist before
this client will connect. Stdio servers run without a shell.
"""
from __future__ import annotations

import shlex

from .mcp import ExternalServer


class RealMCPError(RuntimeError):
    pass


def mcp_tool_spec(client: "RealMCPStdioClient", name: str, description: str = "",
                  risk=None, timeout_seconds: float = 30.0):
    """Adapt one allowlisted MCP tool into a Noesek ToolSpec.

    Default risk is EXTERNAL, so the stage-B policy engine pauses calls for
    approval exactly like any other external tool; operators tune that with
    NOESEK_POLICY_RULES. The MCP server allowlist still applies underneath.
    """
    from pydantic import BaseModel, Field
    from ..core.tools import ToolSpec
    from ..core.types import Risk
    if risk is None: risk = Risk.EXTERNAL

    class McpInput(BaseModel):
        arguments: dict = Field(default_factory=dict)

    async def _call(inp: McpInput):
        content = await client.call_tool(name, inp.arguments)
        return {"content": [getattr(c, "text", str(c)) for c in content] if isinstance(content, list) else str(content)}

    return ToolSpec(f"mcp_{name}", description or f"MCP tool {name} (server {client.server.name})",
                    McpInput, risk, _call, timeout_seconds=timeout_seconds)


class RealMCPStdioClient:
    """MCP stdio client via mcp.client.stdio, enforcing Noesek's allowlist."""

    def __init__(self, server: ExternalServer, timeout: float = 30.0):
        server.validate()
        if server.transport != "stdio":
            raise ValueError("RealMCPStdioClient requires a stdio server")
        if not server.enabled:
            raise PermissionError(f"MCP server is not enabled: {server.name}")
        self.server = server
        self.allowed_tools = set(server.allowed_tools)
        self.timeout = timeout

    async def connect(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        argv = shlex.split(self.server.target)
        if not argv:
            raise RealMCPError("empty stdio command")
        params = StdioServerParameters(command=argv[0], args=argv[1:])
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self.session = await self._session_cm.__aenter__()
        await self.session.initialize()
        return self

    async def close(self):
        if getattr(self, "_session_cm", None):
            await self._session_cm.__aexit__(None, None, None)
        if getattr(self, "_stdio_cm", None):
            await self._stdio_cm.__aexit__(None, None, None)

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exc):
        await self.close()

    async def list_tools(self) -> list[dict]:
        result = await self.session.list_tools()
        return [{"name": t.name, "description": t.description or "",
                 "allowed": t.name in self.allowed_tools} for t in result.tools]

    async def call_tool(self, name: str, arguments: dict | None = None):
        if name not in self.allowed_tools:
            raise PermissionError(f"MCP tool is not allowlisted: {name}")
        result = await self.session.call_tool(name, arguments or {})
        if result.is_error:
            raise RealMCPError(f"tool {name} failed: {result.content}")
        return result.content
