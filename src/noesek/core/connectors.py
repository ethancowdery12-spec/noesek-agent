"""Connector definitions store secret references, never secret values."""
from dataclasses import dataclass,asdict
from urllib.parse import urlparse
@dataclass(frozen=True)
class Connector:
    name:str; kind:str; endpoint:str; secret_ref:str; enabled:bool=False
    def validate(self):
        if self.kind not in {"oauth-device","api-key","aws-profile","mcp-http","mcp-stdio"}: raise ValueError("unsupported connector kind")
        if not self.secret_ref.startswith("vault://"): raise ValueError("secret_ref must be a vault reference")
        if self.endpoint and self.kind!="mcp-stdio" and urlparse(self.endpoint).scheme not in {"https","http"}: raise ValueError("invalid endpoint")
        return self
    def status(self): return {"name":self.name,"kind":self.kind,"endpoint":self.endpoint,"secret_ref":self.secret_ref,"enabled":self.enabled,"credential_value_exposed":False}
