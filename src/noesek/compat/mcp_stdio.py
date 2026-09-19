"""MCP stdio framing without a shell. Executables must be explicitly allowed."""
import asyncio, json, os, struct
from pathlib import Path
class MCPStdioError(RuntimeError): pass
class MCPStdioSession:
    def __init__(self,argv:list[str],allowed_executables:set[str],cwd:Path,timeout:float=30,max_frame:int=2_000_000):
        if not argv or argv[0] not in allowed_executables: raise PermissionError("MCP executable is not allowlisted")
        self.argv,self.cwd,self.timeout,self.max_frame=argv,cwd.resolve(),timeout,max_frame; self.proc=None; self._id=0
    async def start(self):
        if not self.cwd.is_dir(): raise ValueError("cwd must exist")
        env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"HOME":str(self.cwd),"LANG":"C.UTF-8"}
        self.proc=await asyncio.create_subprocess_exec(*self.argv,cwd=self.cwd,env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    async def close(self):
        if self.proc and self.proc.returncode is None: self.proc.terminate(); await self.proc.wait()
    async def rpc(self,method,params=None):
        if not self.proc: raise MCPStdioError("session not started")
        self._id+=1; req={"jsonrpc":"2.0","id":self._id,"method":method};
        if params is not None: req["params"]=params
        payload=json.dumps(req,separators=(",",":")).encode(); self.proc.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode()+payload); await self.proc.stdin.drain()
        header=await asyncio.wait_for(self.proc.stdout.readuntil(b"\r\n\r\n"),self.timeout)
        lengths=[int(x.split(b":",1)[1]) for x in header.split(b"\r\n") if x.lower().startswith(b"content-length:")]
        if len(lengths)!=1 or not 0<=lengths[0]<=self.max_frame: raise MCPStdioError("invalid frame length")
        data=json.loads(await asyncio.wait_for(self.proc.stdout.readexactly(lengths[0]),self.timeout))
        if data.get("id")!=self._id: raise MCPStdioError("response id mismatch")
        if "error" in data: raise MCPStdioError(str(data["error"]))
        return data.get("result")
