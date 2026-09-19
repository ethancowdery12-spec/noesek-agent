"""Versioned Noesek gateway envelope derived from public protocol categories."""
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class GatewayHello:
 protocol:str="noesek-gateway"; version:int=1; client:str="noesek"; capabilities:tuple[str,...]=()
 def negotiate(self,server:dict):
  if server.get("protocol")!=self.protocol or server.get("version")!=self.version: raise ValueError("incompatible gateway protocol")
  return sorted(set(self.capabilities)&set(server.get("capabilities",[])))
def envelope(kind:str,payload:dict,request_id:str):
 if kind not in {"hello","message","event","result","error"} or not request_id: raise ValueError("invalid gateway envelope")
 return {"protocol":"noesek-gateway","version":1,"type":kind,"request_id":request_id,"payload":payload}
