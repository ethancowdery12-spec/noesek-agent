import sys
from pathlib import Path
import pytest
from noesek.core.providers import BedrockAdapter
from noesek.core.usage import normalize_usage
from noesek.core.streaming import parse_sse
from noesek.compat.mcp_stdio import MCPStdioSession

class Client:
    def converse(self,**kw):
        self.kw=kw; return {"output":{"message":{"content":[{"text":"hi"},{"toolUse":{"toolUseId":"1","name":"go","input":{"x":1}}}]}}}
async def test_bedrock_injected_client_normalizes():
    c=Client(); r=await BedrockAdapter(c,"model").complete([{"role":"user","content":"x"}],[])
    assert r.content=="hi" and r.tool_calls[0].name=="go" and c.kw["modelId"]=="model"
def test_usage_normalizes_all_wire_shapes():
    assert normalize_usage("openai",{"prompt_tokens":2,"completion_tokens":3}).total_tokens==5
    assert normalize_usage("anthropic",{"input_tokens":4,"output_tokens":5}).total_tokens==9
    assert normalize_usage("gemini",{"promptTokenCount":6,"candidatesTokenCount":7}).total_tokens==13
    assert normalize_usage("bedrock",{"inputTokens":8,"outputTokens":9}).total_tokens==17
def test_sse_split_chunks_and_cap():
    assert list(parse_sse([b"data: one\n",b"\ndata: two\n\n"]))==["one","two"]
    with pytest.raises(ValueError): list(parse_sse(["data: "+"x"*50],10))
def test_stdio_requires_executable_allowlist(tmp_path):
    with pytest.raises(PermissionError): MCPStdioSession([sys.executable],set(),tmp_path)
