"""Bounded MCP SSE decoder; transport connection is injected by the caller."""
import json
from ..core.streaming import parse_sse
class MCPSSEError(RuntimeError): pass
def decode_mcp_sse(chunks,max_event_bytes=1_000_000):
    for data in parse_sse(chunks,max_event_bytes):
        try: value=json.loads(data)
        except json.JSONDecodeError as e: raise MCPSSEError("invalid JSON event") from e
        if value.get("jsonrpc")!="2.0": raise MCPSSEError("invalid JSON-RPC version")
        yield value
