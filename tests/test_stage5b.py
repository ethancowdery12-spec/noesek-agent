import pytest
from noesek.channels.live import LiveChannelEngine
from noesek.core.backends import LocalTextMedia,RecordingBrowser
from noesek.core.computer_use import ComputerPlan
from noesek.compat.gateway_envelope import GatewayHello,envelope
from noesek.core.otel import OTLPExporter
from noesek.core.telemetry import Span
from noesek.core.peer import PeerOutcome,MoARun,PeerError
class Vault:
 async def resolve(self,r): return "secret"
class Transport:
 async def post(self,url,payload,headers): self.headers=headers; return {"ok":True}
async def test_live_channel_requires_vault_and_host():
 t=Transport(); e=LiveChannelEngine(t,Vault(),{"api.test"}); assert (await e.send("https://api.test/send","vault://x",{}))["ok"]
 with pytest.raises(PermissionError): await e.send("https://evil.test","vault://x",{})
async def test_concrete_safe_backends():
 assert await LocalTextMedia().transcribe(b"hi","text/plain")=="hi"
 p=ComputerPlan("https://x",({"type":"click"},)); b=RecordingBrowser(); assert (await b.execute(p))["recorded"]
def test_gateway_handshake_and_envelope():
 h=GatewayHello(capabilities=("messages","events")); assert h.negotiate({"protocol":"noesek-gateway","version":1,"capabilities":["events"]})==["events"]
 assert envelope("message",{},"1")["version"]==1
async def test_otlp_https_and_redaction():
 t=Transport(); x=OTLPExporter("https://otel.test/v1/traces",t); await x.export([Span("x",{"token":"bad"})]); assert "bad" not in str(t.headers)
 with pytest.raises(ValueError): OTLPExporter("http://x",t)
def test_peer_ownership_and_moa_bounds():
 p=PeerOutcome("u1","u2","do"); p.transfer("u2"); p.accept("u2"); p.complete("u2"); assert p.state=="completed"
 m=MoARun("a",("a","b"),1); assert m.next_round() and not m.next_round()
