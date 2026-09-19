from pathlib import Path
import pytest
from noesek.core.connectors import Connector
from noesek.core.duplex_stream import DuplexStream
from noesek.compat.acp_session import ACPSession,ACPSessionError
from noesek.core.terminal_batch import CommandBatch,execute_approved
from noesek.core.session_portability import import_session,resume_session

def test_connector_requires_vault_reference():
 with pytest.raises(ValueError): Connector("x","api-key","https://x","secret").validate()
 s=Connector("x","api-key","https://x","vault://providers/x").validate().status(); assert s["credential_value_exposed"] is False
async def test_duplex_normalizes_async_transport():
 async def transport(req): yield '{"choices":[{"delta":{"content":"hi"}}]}'
 rows=[x async for x in DuplexStream("openai",transport).run({})]; assert rows[0]["text"]=="hi"
def test_acp_session_lifecycle_and_roots(tmp_path):
 s=ACPSession((tmp_path,),{"fs/read"}); s.initialize(); assert s.authorize("fs/read",str(tmp_path/"x"))
 with pytest.raises(PermissionError): s.authorize("fs/read","/etc/passwd")
 s.close()
 with pytest.raises(ACPSessionError): s.authorize("fs/read")
async def test_terminal_batch_digest_gates_backend(tmp_path):
 class Backend:
  async def run(self,b): return {"ok":True}
 b=CommandBatch("python:3.12",(("python","-V"),),str(tmp_path)); assert (await execute_approved(b,b.digest,Backend()))["ok"]
 with pytest.raises(PermissionError): await execute_approved(b,"bad",Backend())
def test_terminal_batch_rejects_network(tmp_path):
 with pytest.raises(ValueError): CommandBatch("x",(("true",),),str(tmp_path),True)
async def test_session_import_and_resume(db):
 cid=await import_session({"format":"noesek-session-v1","messages":[{"role":"user","content":"hi"}]},"import","new")
 assert await resume_session("import","new")==cid
 with pytest.raises(ValueError): await import_session({"format":"noesek-session-v1","messages":[]},"import","new")
