import json
import httpx, pytest
from noesek.core.providers import AnthropicAdapter, GeminiAdapter, FailoverLLM, ProviderError
from noesek.compat.mcp_client import MCPClient, MCPError

class FakeClient:
    def __init__(self,response): self.response=response; self.request=None
    async def __aenter__(self): return self
    async def __aexit__(self,*a): pass
    async def post(self,url,**kwargs): self.request=(url,kwargs); return self.response

def response(code,data): return httpx.Response(code,json=data,request=httpx.Request("POST","https://x"))

async def test_anthropic_normalizes_text_and_tool(monkeypatch):
    fake=FakeClient(response(200,{"content":[{"type":"text","text":"ok"},{"type":"tool_use","id":"c1","name":"search","input":{"q":"x"}}]}))
    monkeypatch.setattr(httpx,"AsyncClient",lambda **k:fake)
    r=await AnthropicAdapter("k","m","https://a").complete([{"role":"system","content":"s"},{"role":"user","content":"u"}],[])
    assert r.content=="ok" and r.tool_calls[0].arguments=={"q":"x"}
    assert fake.request[1]["headers"]["anthropic-version"]=="2023-06-01"

async def test_gemini_normalizes_function_call(monkeypatch):
    fake=FakeClient(response(200,{"candidates":[{"content":{"parts":[{"functionCall":{"name":"go","args":{"n":1}}}]}}]}))
    monkeypatch.setattr(httpx,"AsyncClient",lambda **k:fake)
    r=await GeminiAdapter("k","m","https://g").complete([{"role":"user","content":"u"}],[])
    assert r.tool_calls[0].name=="go" and fake.request[1]["params"]=={"key":"k"}

async def test_failover_succeeds_after_server_error():
    class A:
        async def complete(self,m,t): raise ProviderError("HTTP 503")
    class B:
        async def complete(self,m,t): return "ok"
    assert await FailoverLLM([A(),B()]).complete([],[])=="ok"

async def test_failover_stops_on_auth_error():
    class A:
        async def complete(self,m,t): raise ProviderError("HTTP 401")
    class B:
        async def complete(self,m,t): raise AssertionError
    with pytest.raises(ProviderError): await FailoverLLM([A(),B()]).complete([],[])

async def test_mcp_lists_and_marks_allowlist(monkeypatch):
    fake=FakeClient(response(200,{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"read"},{"name":"write"}]}}))
    monkeypatch.setattr(httpx,"AsyncClient",lambda **k:fake)
    rows=await MCPClient("https://mcp.test",{"read"}).list_tools()
    assert [x["allowed"] for x in rows]==[True,False]

async def test_mcp_denies_before_network(monkeypatch):
    client=MCPClient("https://mcp.test",set())
    with pytest.raises(PermissionError): await client.call_tool("write",{})

async def test_mcp_checks_response_id(monkeypatch):
    fake=FakeClient(response(200,{"jsonrpc":"2.0","id":99,"result":{}})); monkeypatch.setattr(httpx,"AsyncClient",lambda **k:fake)
    with pytest.raises(MCPError): await MCPClient("https://mcp.test",set()).list_tools()

def test_configured_llm_selects_native_adapter(monkeypatch):
    from noesek.config import settings
    from noesek.core.llm import configured_llm
    old=settings.llm_provider
    try:
        settings.llm_provider="anthropic"; assert isinstance(configured_llm(),AnthropicAdapter)
        settings.llm_provider="gemini"; assert isinstance(configured_llm(),GeminiAdapter)
        settings.llm_provider="unknown"
        with pytest.raises(ValueError): configured_llm()
    finally: settings.llm_provider=old
