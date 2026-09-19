from typing import Protocol,AsyncIterator
class SourceAdapter(Protocol):
    async def start(self,cursor:str|None)->None: ...
    def events(self)->AsyncIterator[dict]: ...
    async def checkpoint(self)->str|None: ...
    async def close(self)->None: ...
class ManagedSource:
    def __init__(self,adapter:SourceAdapter): self.adapter,self.started,self.closed=adapter,False,False
    async def start(self,cursor=None):
        if self.started: return
        await self.adapter.start(cursor); self.started=True
    async def stop(self):
        if self.closed:return
        await self.adapter.close(); self.closed=True
