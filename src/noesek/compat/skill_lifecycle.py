"""Install and manage inert skill packages without executing their contents."""
from pathlib import Path
from hashlib import sha256
import shutil,re
_NAME=re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
class SkillError(RuntimeError): pass
class SkillStore:
    def __init__(self,root:Path): self.root=root.resolve(); self.root.mkdir(parents=True,exist_ok=True); self.enabled=set()
    def install(self,source:Path,name:str):
        if not _NAME.fullmatch(name): raise SkillError("invalid skill name")
        src=source.resolve(); md=src/"SKILL.md"
        if not md.is_file(): raise SkillError("SKILL.md is required")
        for f in src.rglob("*"):
            if f.is_symlink(): raise SkillError("symlinks are not allowed")
        dest=self.root/name
        if dest.exists(): raise SkillError("skill already installed")
        shutil.copytree(src,dest)
        digest=sha256(b"".join(f.read_bytes() for f in sorted(dest.rglob("*")) if f.is_file())).hexdigest()
        return {"name":name,"digest":digest,"enabled":False}
    def enable(self,name):
        if not (self.root/name/"SKILL.md").is_file(): raise SkillError("skill is not installed")
        self.enabled.add(name)
    def disable(self,name): self.enabled.discard(name)
    def remove(self,name): self.disable(name); shutil.rmtree(self.root/name,ignore_errors=True)
