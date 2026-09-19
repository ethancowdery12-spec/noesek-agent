import pytest
from noesek.core.auth import DeviceAuthorization,complete_device_flow,auth_status,DeviceFlowError
from noesek.core.stream_events import normalize_stream
from noesek.compat.mcp_sse import decode_mcp_sse,MCPSSEError
from noesek.compat.acp import ACPCodec,ACPError
class Store:
 def __init__(self): self.data={}
 async def put(self,n,v): self.data[n]=v
 async def exists(self,n): return n in self.data
async def test_device_flow_stores_but_does_not_return_token():
 s=Store(); replies=iter([{"error":"authorization_pending"},{"access_token":"secret"}])
 async def poll(code): return next(replies)
 async def sleep(n): pass
 now=iter([0,0,1]); r=await complete_device_flow(DeviceAuthorization("d","u","https://verify",100,1),poll,s,"provider/token",sleep,lambda:next(now))
 assert r=={"connected":True,"secret_name":"provider/token","token_stored":True} and s.data["provider/token"]=="secret"
 assert await auth_status(s,"provider/token")=={"connected":True,"secret_name":"provider/token"}
def test_stream_normalization():
 assert normalize_stream("openai",{"choices":[{"delta":{"content":"hi"}}]})[0]["text"]=="hi"
 assert normalize_stream("anthropic",{"type":"content_block_delta","delta":{"type":"text_delta","text":"a"}})[0]["text"]=="a"
 assert normalize_stream("gemini",{"candidates":[{"content":{"parts":[{"text":"g"}]}}]})[0]["text"]=="g"
def test_mcp_sse_validates_rpc():
 assert list(decode_mcp_sse([b'data: {"jsonrpc":"2.0","id":1}\n\n']))[0]["id"]==1
 with pytest.raises(MCPSSEError): list(decode_mcp_sse([b'data: {}\n\n']))
def test_acp_codec_allowlist_and_limits():
 c=ACPCodec({"session/new"},100); m={"jsonrpc":"2.0","id":1,"method":"session/new"}; assert c.decode(c.encode(m))["id"]==1
 with pytest.raises(PermissionError): c.encode({"jsonrpc":"2.0","method":"fs/write"})
 with pytest.raises(ACPError): ACPCodec(set(),2).decode(b'{}\n')
