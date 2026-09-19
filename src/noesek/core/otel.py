"""Minimal OTLP/HTTP JSON exporter with injected transport and redacted spans."""
from .telemetry import Span
class OTLPExporter:
 def __init__(self,endpoint,transport,headers=None):
  if not endpoint.startswith("https://"): raise ValueError("OTLP endpoint must use HTTPS")
  self.endpoint,self.transport,self.headers=endpoint,transport,headers or {}
 async def export(self,spans:list[Span]):
  payload={"resourceSpans":[{"scopeSpans":[{"spans":[s.export() for s in spans]}]}]}
  return await self.transport.post(self.endpoint,payload,self.headers)
