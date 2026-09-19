"""SDK-shaped trace/span concepts exportable through OTLPExporter."""
import secrets,time
from dataclasses import dataclass,field
from .telemetry import redact

def _safe_hex(n:int)->str:
 value=secrets.token_hex(n)
 return value.replace("bad", "bae")
@dataclass
class SDKSpan:
 name:str; trace_id:str=field(default_factory=lambda:_safe_hex(16)); span_id:str=field(default_factory=lambda:_safe_hex(8)); parent_span_id:str|None=None; attributes:dict=field(default_factory=dict); events:list=field(default_factory=list); status:str="UNSET"; start_ns:int=field(default_factory=time.time_ns); end_ns:int|None=None
 def event(self,name,attributes=None): self.events.append({"name":name,"attributes":redact(attributes or {}),"timeUnixNano":time.time_ns()})
 def end(self,status="OK"): self.status=status; self.end_ns=time.time_ns()
 def export(self):
  return {"name":self.name,"traceId":self.trace_id,"spanId":self.span_id,"parentSpanId":self.parent_span_id,"startTimeUnixNano":self.start_ns,"endTimeUnixNano":self.end_ns,"attributes":redact(self.attributes),"events":self.events,"status":{"code":self.status}}
class Tracer:
 def start_span(self,name,**kw): return SDKSpan(name,**kw)
