"""Trusted plugin lifecycle. Verification is injected; discovery never imports plugin code."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
class PluginTrustError(RuntimeError): pass
@dataclass(frozen=True)
class PluginPolicy:
    trusted_publishers:frozenset[str]; allowed_capabilities:frozenset[str]
def canonical_manifest(data:dict)->bytes: return json.dumps(data,sort_keys=True,separators=(",",":")).encode()
def verify_plugin(directory:Path,policy:PluginPolicy,verify_signature):
    root=directory.resolve(); mf=(root/"noesek-plugin.json").resolve()
    if root not in mf.parents: raise PluginTrustError("manifest escapes plugin root")
    data=json.loads(mf.read_text()); publisher=data.get("publisher","")
    if publisher not in policy.trusted_publishers: raise PluginTrustError("publisher is not trusted")
    caps=frozenset(data.get("capabilities",[]))
    if not caps<=policy.allowed_capabilities: raise PluginTrustError("capability is not allowed")
    signature=data.pop("signature",None)
    if not signature or not verify_signature(publisher,canonical_manifest(data),signature): raise PluginTrustError("invalid signature")
    files=[]
    for f in sorted(root.rglob("*")):
        if f.is_symlink(): raise PluginTrustError("symlinks are not allowed")
        if f.is_file() and f!=mf: files.append((str(f.relative_to(root)),sha256(f.read_bytes()).hexdigest()))
    digest=sha256(canonical_manifest(data)+canonical_manifest({"files":files})).hexdigest()
    return {"name":data["name"],"publisher":publisher,"capabilities":sorted(caps),"digest":digest,"verified":True,"enabled":False}
class PluginRegistry:
    def __init__(self): self.records={}
    def install(self,record): self.records[record["name"]]=dict(record); return self.records[record["name"]]
    def enable(self,name,digest):
        row=self.records[name]
        if row["digest"]!=digest or not row["verified"]: raise PluginTrustError("plugin changed after verification")
        row["enabled"]=True
    def disable(self,name): self.records[name]["enabled"]=False
    def remove(self,name): self.records.pop(name,None)
