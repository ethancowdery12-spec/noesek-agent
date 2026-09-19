from dataclasses import dataclass,asdict,field
from datetime import datetime,timezone
import json,re,uuid
_SECRET=re.compile(r'(?i)(authorization|api[_-]?key|token|password)')
def redact(attrs): return {k:("[REDACTED]" if _SECRET.search(k) else v) for k,v in attrs.items()}
@dataclass
class Span:
 name:str; attributes:dict; trace_id:str=field(default_factory=lambda:uuid.uuid4().hex); started_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat()); ended_at:str|None=None
 def finish(self): self.ended_at=datetime.now(timezone.utc).isoformat()
 def export(self):
  row=asdict(self); row["attributes"]=redact(row["attributes"]); return row
class JsonTelemetry:
 def __init__(self,sink,max_spans=10000): self.sink,self.count,self.max_spans=sink,0,max_spans
 def emit(self,span:Span):
  if self.count>=self.max_spans: raise RuntimeError("telemetry limit reached")
  self.sink.write(json.dumps(span.export(),sort_keys=True)+"\n"); self.count+=1
