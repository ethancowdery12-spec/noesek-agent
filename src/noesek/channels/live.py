"""Authenticated send engine with injected transport and vault resolver."""
class LiveChannelEngine:
 def __init__(self,transport,vault,allowed_hosts:set[str]): self.transport,self.vault,self.allowed_hosts=transport,vault,allowed_hosts
 async def send(self,endpoint:str,secret_ref:str,payload:dict):
  from urllib.parse import urlparse
  if urlparse(endpoint).hostname not in self.allowed_hosts: raise PermissionError("channel host is not allowed")
  if not secret_ref.startswith("vault://"): raise ValueError("vault secret reference required")
  token=await self.vault.resolve(secret_ref)
  try: return await self.transport.post(endpoint,payload,{"Authorization":f"Bearer {token}"})
  finally: token=None
