from dataclasses import dataclass,field
class PeerError(RuntimeError): pass
@dataclass
class PeerOutcome:
 initiating_owner:str; outcome_owner:str; request:str; max_hops:int=4; accepted_by:str|None=None; hops:list[str]=field(default_factory=list); state:str="proposed"
 def transfer(self,peer:str):
  if self.state not in {"proposed","accepted"} or len(self.hops)>=self.max_hops or peer in self.hops: raise PeerError("invalid or looping transfer")
  self.hops.append(peer)
 def accept(self,peer:str):
  if peer!=self.outcome_owner: raise PermissionError("only outcome owner may accept")
  self.accepted_by=peer; self.state="accepted"
 def complete(self,peer:str):
  if self.state!="accepted" or peer!=self.outcome_owner: raise PermissionError("accepted outcome owner required")
  self.state="completed"
@dataclass
class MoARun:
 coordinator:str; members:tuple[str,...]; max_rounds:int=3; round:int=0
 def next_round(self):
  if self.round>=self.max_rounds: return False
  self.round+=1; return True
