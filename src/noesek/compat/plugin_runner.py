"""Isolated plugin invocation contract. The backend owns OS/container isolation."""
import json
class PluginRunner:
    def __init__(self,backend,max_request=1_000_000,max_response=2_000_000): self.backend,self.max_request,self.max_response=backend,max_request,max_response
    async def invoke(self,verified_record:dict,capability:str,payload:dict):
        if not verified_record.get("verified") or not verified_record.get("enabled"): raise PermissionError("plugin is not verified and enabled")
        if capability not in verified_record.get("capabilities",[]): raise PermissionError("capability is not declared")
        request=json.dumps({"plugin":verified_record["name"],"digest":verified_record["digest"],"capability":capability,"payload":payload},separators=(",",":")).encode()
        if len(request)>self.max_request: raise ValueError("plugin request exceeds limit")
        raw=await self.backend.run(request,network=False,read_only=True)
        if len(raw)>self.max_response: raise ValueError("plugin response exceeds limit")
        return json.loads(raw)
