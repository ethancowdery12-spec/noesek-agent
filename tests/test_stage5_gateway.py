import io,pytest
from noesek.channels.slack import SlackEventsAdapter
from noesek.channels.telegram import TelegramWebhookAdapter
from noesek.core.media import MediaPolicy,ingest_media
from noesek.core.computer_use import ComputerPlan,execute_plan
from noesek.core.teams import TeamRun,TeamError
from noesek.core.telemetry import Span,JsonTelemetry
async def test_slack_and_telegram_normalize_nonlive():
 s=await SlackEventsAdapter().normalize({"event_id":"e","event":{"type":"message","user":"u","channel":"c","text":"hi"}}); assert s[0].text=="hi"
 t=await TelegramWebhookAdapter().normalize({"update_id":1,"message":{"from":{"id":2},"chat":{"id":3},"text":"yo"}}); assert t[0].conversation=="3"
async def test_media_scan_precedes_processor():
 class Scan:
  async def clean(self,*a): return True
 class Proc:
  async def process(self,*a): return "text"
 r=await ingest_media(b"x","audio/wav",MediaPolicy(frozenset({"audio/wav"}),10),Scan(),Proc()); assert r["result"]=="text"
async def test_computer_plan_digest_and_origin():
 p=ComputerPlan("https://example.com/a",({"type":"click","selector":"#x"},)).validate({"https://example.com"},{"click"})
 class E:
  async def run(self,p): return {"ok":True}
 assert (await execute_plan(p,p.digest,E()))["ok"]
 with pytest.raises(PermissionError): await execute_plan(p,"bad",E())
def test_team_owner_and_termination():
 t=TeamRun("ship","lead",("lead","worker"),1); t.report("worker",{}); assert t.state=="terminated"
 with pytest.raises(TeamError): TeamRun("x","none",("lead",))
def test_telemetry_redacts_secrets():
 sink=io.StringIO(); s=Span("call",{"api_key":"secret","status":"ok"}); s.finish(); JsonTelemetry(sink).emit(s); assert "secret" not in sink.getvalue() and "REDACTED" in sink.getvalue()
