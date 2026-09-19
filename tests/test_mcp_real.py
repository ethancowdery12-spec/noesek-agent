"""Real MCP stdio client over the official SDK, behind Noesek's server policy."""
import sys
from pathlib import Path
import pytest
from noesek.compat.mcp import ExternalServer
from noesek.compat.mcp_real import RealMCPStdioClient

SERVER = '''
from mcp.server.mcpserver import MCPServer
mcp = MCPServer("noesek-test")

@mcp.tool()
def echo(text: str) -> str:
    return text

@mcp.tool()
def hidden() -> str:
    return "should never run"

mcp.run()
'''

def _server(tmp_path, **kw):
    script = tmp_path / "srv.py"; script.write_text(SERVER)
    return ExternalServer(name="t", transport="stdio",
                          target=f"{sys.executable} {script}", enabled=True, **kw)

async def test_real_mcp_roundtrip_and_allowlist(tmp_path):
    server = _server(tmp_path, allowed_tools=("echo",))
    async with RealMCPStdioClient(server) as client:
        tools = await client.list_tools()
        by_name = {t["name"]: t for t in tools}
        assert by_name["echo"]["allowed"] is True
        assert by_name["hidden"]["allowed"] is False
        content = await client.call_tool("echo", {"text": "hi noesek"})
        assert any("hi noesek" in getattr(c, "text", "") for c in content)
        with pytest.raises(PermissionError):
            await client.call_tool("hidden", {})

def test_disabled_server_refused(tmp_path):
    server = _server(tmp_path, allowed_tools=("echo",))
    object.__setattr__(server, "enabled", False)
    with pytest.raises(PermissionError):
        RealMCPStdioClient(server)
