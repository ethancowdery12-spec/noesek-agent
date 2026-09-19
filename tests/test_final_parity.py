import io,wave
from datetime import datetime,timezone
from pathlib import Path
import pytest
from noesek.compat.upstream_contract import contract_report
from noesek.core.backends import WavMetadataBackend,OfflineHTMLBrowser
from noesek.core.computer_use import ComputerPlan
from noesek.core.peer_transport import PeerEnvelope,ReplayCache,verify_envelope
from noesek.core.otel_sdk import Tracer

def test_pinned_public_contract_has_no_code_side_gaps(): assert contract_report()["missing"]==[]
async def test_wav_backend_safe_metadata():
 b=io.BytesIO()
 with wave.open(b,"wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0"*800)
 r=await WavMetadataBackend().transcribe(b.getvalue(),"audio/wav"); assert r["duration_seconds"]==.1
async def test_offline_html_browser(tmp_path):
 f=tmp_path/"x.html"; f.write_text('<h1>Hello</h1><a href="/x">X</a>'); p=ComputerPlan(f"file://{f}",({"type":"read"},)); r=await OfflineHTMLBrowser().execute(p); assert "Hello" in r["text"] and r["links"]==["/x"]
def test_peer_signature_timestamp_and_replay():
 now=datetime.now(timezone.utc); e=PeerEnvelope("a","b","n",now.isoformat(),{"x":1},"ok"); cache=ReplayCache(); verifier=lambda s,b,sig:sig=="ok"
 assert verify_envelope(e,"b",verifier,cache,now)=={"x":1}
 with pytest.raises(PermissionError): verify_envelope(e,"b",verifier,cache,now)
def test_sdk_span_ids_events_status_redaction():
 s=Tracer().start_span("x",attributes={"token":"bad"}); s.event("call",{"api_key":"bad"}); s.end(); x=s.export(); assert len(x["traceId"])==32 and len(x["spanId"])==16 and "bad" not in str(x)
