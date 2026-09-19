from dataclasses import dataclass
from hashlib import sha256
import json
from urllib.parse import urlparse
@dataclass(frozen=True)
class ComputerPlan:
 origin:str; actions:tuple[dict,...]
 def validate(self,allowed_origins:set[str],allowed_actions:set[str],max_actions=50):
  origin=f"{urlparse(self.origin).scheme}://{urlparse(self.origin).netloc}"
  if origin not in allowed_origins: raise PermissionError("origin is not allowed")
  if not 0<len(self.actions)<=max_actions or any(a.get("type") not in allowed_actions for a in self.actions): raise PermissionError("action plan is not allowed")
  return self
 @property
 def digest(self): return sha256(json.dumps({"origin":self.origin,"actions":self.actions},sort_keys=True).encode()).hexdigest()
async def execute_plan(plan,approved_digest,executor):
 if plan.digest!=approved_digest: raise PermissionError("plan differs from approval")
 return await executor.run(plan)
