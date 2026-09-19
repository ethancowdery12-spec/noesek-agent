"""Bounded ACP-style JSON-lines codec with explicit method allowlist."""
import json
class ACPError(RuntimeError): pass
class ACPCodec:
    def __init__(self,allowed_methods:set[str],max_bytes:int=1_000_000): self.allowed_methods,self.max_bytes=set(allowed_methods),max_bytes
    def encode(self,message:dict)->bytes:
        method=message.get("method")
        if method and method not in self.allowed_methods: raise PermissionError(f"ACP method is not allowlisted: {method}")
        raw=json.dumps(message,separators=(",",":")).encode()+b"\n"
        if len(raw)>self.max_bytes: raise ACPError("message exceeds limit")
        return raw
    def decode(self,line:bytes)->dict:
        if len(line)>self.max_bytes: raise ACPError("message exceeds limit")
        try: value=json.loads(line)
        except json.JSONDecodeError as e: raise ACPError("invalid JSON") from e
        if not isinstance(value,dict) or value.get("jsonrpc")!="2.0": raise ACPError("invalid message")
        method=value.get("method")
        if method and method not in self.allowed_methods: raise PermissionError(f"ACP method is not allowlisted: {method}")
        return value
