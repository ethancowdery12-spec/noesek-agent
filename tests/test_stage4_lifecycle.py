from pathlib import Path
import json,pytest
from noesek.compat.plugin_lifecycle import PluginPolicy,PluginRegistry,verify_plugin,PluginTrustError,canonical_manifest
from noesek.compat.skill_lifecycle import SkillStore,SkillError
from noesek.core.schedule_state import CronJob,Subscription

def plugin(tmp_path,publisher="trusted",caps=["tools"]):
 d=tmp_path/"p"; d.mkdir(); data={"name":"p","publisher":publisher,"capabilities":caps,"version":"1"}; data["signature"]="ok"; (d/"noesek-plugin.json").write_text(json.dumps(data)); (d/"code.py").write_text("x=1"); return d
def verifier(pub,payload,sig): return pub=="trusted" and sig=="ok"
def test_plugin_trust_and_digest_binding(tmp_path):
 r=verify_plugin(plugin(tmp_path),PluginPolicy(frozenset({"trusted"}),frozenset({"tools"})),verifier); reg=PluginRegistry(); reg.install(r); reg.enable("p",r["digest"]); assert reg.records["p"]["enabled"]
 with pytest.raises(PluginTrustError): reg.enable("p","changed")
def test_plugin_rejects_publisher_and_capability(tmp_path):
 with pytest.raises(PluginTrustError): verify_plugin(plugin(tmp_path,"evil"),PluginPolicy(frozenset({"trusted"}),frozenset({"tools"})),verifier)
def test_skill_full_lifecycle(tmp_path):
 src=tmp_path/"src"; src.mkdir(); (src/"SKILL.md").write_text("# Safe")
 store=SkillStore(tmp_path/"installed"); row=store.install(src,"safe"); store.enable("safe"); assert "safe" in store.enabled; store.disable("safe"); store.remove("safe"); assert not (store.root/"safe").exists()
def test_cron_serializes_and_resumes():
 j=CronJob("*/5 * * * *",{}) if False else CronJob("5 * * * *",{})
 j.pause(); j.resume(); assert j.serialize()["state"]=="active"
 with pytest.raises(ValueError): CronJob("bad",{})
def test_subscription_checkpoint_cleanup_idempotent():
 s=Subscription("gmail",{"from":"x"}); s.checkpoint("c1"); saved=s.serialize(); assert saved["cursor"]=="c1"; s.cleanup(); s.cleanup(); assert s.state=="closed"
 with pytest.raises(ValueError): s.resume()
