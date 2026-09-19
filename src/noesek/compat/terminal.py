"""Bounded local command runner. It is not wired as a READ tool."""
import asyncio, os, shlex
from pathlib import Path

class TerminalPolicyError(ValueError): pass
_DENIED = {"sudo","su","ssh","scp","nc","ncat","curl","wget","powershell","pwsh"}

def validate_command(argv: list[str], workspace: Path) -> tuple[list[str], Path]:
    if not argv or argv[0] in _DENIED: raise TerminalPolicyError("command is empty or denied")
    if any("\x00" in part for part in argv): raise TerminalPolicyError("NUL is not allowed")
    root=workspace.expanduser().resolve()
    if not root.is_dir(): raise TerminalPolicyError("workspace must exist")
    return argv, root

async def run_command(argv: list[str], workspace: Path, timeout: float=30, max_output: int=100_000) -> dict:
    argv, root=validate_command(argv, workspace)
    env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"HOME":str(root),"LANG":"C.UTF-8"}
    proc=await asyncio.create_subprocess_exec(*argv,cwd=root,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try: out,err=await asyncio.wait_for(proc.communicate(),timeout)
    except TimeoutError:
        proc.kill(); await proc.wait(); return {"exit_code":None,"timed_out":True,"stdout":"","stderr":""}
    return {"exit_code":proc.returncode,"timed_out":False,"stdout":out[:max_output].decode(errors="replace"),"stderr":err[:max_output].decode(errors="replace"),"truncated":len(out)>max_output or len(err)>max_output}
