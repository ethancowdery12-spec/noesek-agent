"""Small MCP JSON-RPC client over HTTP. Every callable tool needs an allowlist entry."""
import itertools
import httpx

class MCPError(RuntimeError): pass
class MCPClient:
    def __init__(self,url: str,allowed_tools: set[str],timeout: float=30,headers: dict[str,str]|None=None):
        if not url.startswith(("http://","https://")): raise ValueError("HTTP(S) MCP URL required")
        self.url,self.allowed_tools,self.timeout,self.headers=url,set(allowed_tools),timeout,headers or {}; self._ids=itertools.count(1)
    async def _rpc(self,method: str,params: dict|None=None):
        rid=next(self._ids); payload={"jsonrpc":"2.0","id":rid,"method":method}
        if params is not None: payload["params"]=params
        async with httpx.AsyncClient(timeout=self.timeout) as client: r=await client.post(self.url,json=payload,headers=self.headers)
        r.raise_for_status(); data=r.json()
        if data.get("id") != rid: raise MCPError("response id mismatch")
        if "error" in data: raise MCPError(str(data["error"]))
        return data.get("result")
    async def initialize(self):
        return await self._rpc("initialize",{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"noesek","version":"1.0.0"}})
    async def list_tools(self):
        result=await self._rpc("tools/list",{}); rows=result.get("tools",[]) if isinstance(result,dict) else []
        return [{**r,"allowed":r.get("name") in self.allowed_tools} for r in rows]
    async def call_tool(self,name: str,arguments: dict):
        if name not in self.allowed_tools: raise PermissionError(f"MCP tool is not allowlisted: {name}")
        return await self._rpc("tools/call",{"name":name,"arguments":arguments})
