import json
from datetime import datetime,timezone
import pytest
from noesek.compat.plugin_runner import PluginRunner
from noesek.compat.catalog import ingest_catalog,CatalogError
from noesek.compat.skill_review import SkillProposal
from noesek.core.cron import CronExpression,CronDispatcher
from noesek.core.source_adapter import ManagedSource
class Backend:
 async def run(self,request,**kw): self.kw=kw; return b'{"ok":true}'
async def test_plugin_runner_requires_enabled_and_isolation_flags():
 b=Backend(); r={"name":"p","digest":"d","verified":True,"enabled":True,"capabilities":["tools"]}; assert (await PluginRunner(b).invoke(r,"tools",{}))["ok"] and b.kw=={"network":False,"read_only":True}
 with pytest.raises(PermissionError): await PluginRunner(b).invoke({**r,"enabled":False},"tools",{})
def test_signed_catalog_requires_pins_and_https():
 raw=json.dumps({"plugins":[{"name":"p","version":"1","url":"https://x/p","sha256":"a"*64}]}).encode(); out=ingest_catalog(raw,"s","pub",{"pub"},lambda *x:True); assert out["plugins"][0]["name"]=="p"
 with pytest.raises(CatalogError): ingest_catalog(raw,"s","bad",{"pub"},lambda *x:True)
def test_learned_skill_needs_evidence_and_review():
 p=SkillProposal("x","# x",["session:1"]); assert p.decide(True,"human")["state"]=="approved"
 with pytest.raises(ValueError): SkillProposal("x","",[])
def test_cron_steps_ranges_and_dedupes():
 e=CronExpression.parse("*/15 9-17 * * 1-5"); dt=datetime(2026,9,17,9,30,tzinfo=timezone.utc); assert e.matches(dt)
 d=CronDispatcher(); job={"job_id":"1","state":"active","expression":"*/15 9-17 * * 1-5"}; assert len(d.due([job],dt))==1 and d.due([job],dt)==[]
class Adapter:
 def __init__(self): self.started=0; self.closed=0
 async def start(self,c): self.started+=1; self.cursor=c
 async def close(self): self.closed+=1
async def test_managed_source_start_stop_idempotent():
 a=Adapter(); m=ManagedSource(a); await m.start("c"); await m.start("x"); await m.stop(); await m.stop(); assert (a.started,a.closed,a.cursor)==(1,1,"c")
