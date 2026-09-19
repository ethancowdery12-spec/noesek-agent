"""Immutable command batches separate approval from container execution."""
from dataclasses import dataclass
from hashlib import sha256
import json
@dataclass(frozen=True)
class CommandBatch:
    image:str; commands:tuple[tuple[str,...],...]; workspace:str; network:bool=False
    def __post_init__(self):
        if not self.image or not self.commands or any(not c for c in self.commands): raise ValueError("image and commands are required")
        if self.network: raise ValueError("network-enabled batches are not supported")
    @property
    def digest(self): return sha256(json.dumps({"image":self.image,"commands":self.commands,"workspace":self.workspace,"network":self.network},sort_keys=True).encode()).hexdigest()
async def execute_approved(batch:CommandBatch,approved_digest:str,backend):
    if approved_digest!=batch.digest: raise PermissionError("batch differs from approved commands")
    return await backend.run(batch)
