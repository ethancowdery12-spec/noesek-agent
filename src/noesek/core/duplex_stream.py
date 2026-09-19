"""Transport-injected duplex stream with bounded input and normalized event output."""
import json
from .stream_events import normalize_stream
class DuplexStream:
    def __init__(self,provider:str,transport,max_event_bytes:int=1_000_000): self.provider,self.transport,self.max_event_bytes=provider,transport,max_event_bytes
    async def run(self,request:dict):
        async for raw in self.transport(request):
            if isinstance(raw,bytes): raw=raw.decode(errors="replace")
            if len(raw.encode())>self.max_event_bytes: raise ValueError("stream event exceeds limit")
            event=json.loads(raw) if isinstance(raw,str) else raw
            for normalized in normalize_stream(self.provider,event): yield normalized
