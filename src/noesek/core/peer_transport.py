"""Authenticated peer envelope with injected verifier and bounded replay cache."""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone,timedelta
import json
@dataclass(frozen=True)
class PeerEnvelope:
 sender:str; recipient:str; nonce:str; sent_at:str; body:dict; signature:str
 def signed_bytes(self): return json.dumps({"sender":self.sender,"recipient":self.recipient,"nonce":self.nonce,"sent_at":self.sent_at,"body":self.body},sort_keys=True,separators=(",",":")).encode()
class ReplayCache:
 def __init__(self,max_entries=10000): self.max_entries=max_entries; self.seen=set()
 def accept(self,nonce):
  if nonce in self.seen: return False
  if len(self.seen)>=self.max_entries: raise RuntimeError("replay cache full")
  self.seen.add(nonce); return True
def verify_envelope(e:PeerEnvelope,expected_recipient:str,verifier,cache:ReplayCache,now:datetime,max_age=timedelta(minutes=5)):
 if e.recipient!=expected_recipient: raise PermissionError("wrong recipient")
 ts=datetime.fromisoformat(e.sent_at)
 if ts.tzinfo is None or abs(now.astimezone(timezone.utc)-ts.astimezone(timezone.utc))>max_age: raise PermissionError("stale peer message")
 if not verifier(e.sender,e.signed_bytes(),e.signature): raise PermissionError("invalid peer signature")
 if not cache.accept(e.nonce): raise PermissionError("replayed peer message")
 return e.body
