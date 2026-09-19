"""Bounded ACP session state: explicit roots, lifecycle and method permissions."""
from dataclasses import dataclass,field
from pathlib import Path
import uuid
class ACPSessionError(RuntimeError): pass
@dataclass
class ACPSession:
    roots:tuple[Path,...]; allowed_methods:set[str]; session_id:str=field(default_factory=lambda:str(uuid.uuid4())); state:str="new"
    def __post_init__(self): self.roots=tuple(p.resolve() for p in self.roots)
    def initialize(self):
        if self.state!="new": raise ACPSessionError("session already initialized")
        self.state="ready"; return {"sessionId":self.session_id,"roots":[str(p) for p in self.roots]}
    def authorize(self,method:str,path:str|None=None):
        if self.state!="ready": raise ACPSessionError("session is not ready")
        if method not in self.allowed_methods: raise PermissionError("ACP method is not allowed")
        if path is not None:
            target=Path(path).resolve()
            if not any(target==r or r in target.parents for r in self.roots): raise PermissionError("path is outside ACP roots")
        return True
    def close(self): self.state="closed"
