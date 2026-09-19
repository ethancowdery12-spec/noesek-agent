class MediaBackend:
 async def transcribe(self,data:bytes,content_type:str): raise NotImplementedError
 async def synthesize(self,text:str,voice:str): raise NotImplementedError
class BrowserBackend:
 async def execute(self,plan): raise NotImplementedError
class LocalTextMedia(MediaBackend):
 async def transcribe(self,data,content_type):
  if content_type!="text/plain": raise ValueError("local backend supports text/plain only")
  return data.decode("utf-8",errors="replace")
 async def synthesize(self,text,voice): raise NotImplementedError("no local speech engine configured")
class RecordingBrowser(BrowserBackend):
 def __init__(self): self.plans=[]
 async def execute(self,plan): self.plans.append(plan); return {"recorded":True,"actions":len(plan.actions)}

class WavMetadataBackend(MediaBackend):
 async def transcribe(self,data,content_type):
  import io,wave
  if content_type!="audio/wav": raise ValueError("WAV required")
  with wave.open(io.BytesIO(data),"rb") as w: return {"frames":w.getnframes(),"rate":w.getframerate(),"channels":w.getnchannels(),"duration_seconds":w.getnframes()/w.getframerate()}
 async def synthesize(self,text,voice): raise NotImplementedError("no speech synthesizer configured")

class OfflineHTMLBrowser(BrowserBackend):
 """Read-only local HTML inspection; no network, script, cookie or file mutation."""
 async def execute(self,plan):
  from html.parser import HTMLParser
  from pathlib import Path
  class P(HTMLParser):
   def __init__(self): super().__init__(); self.text=[]; self.links=[]
   def handle_data(self,d):
    if d.strip(): self.text.append(d.strip())
   def handle_starttag(self,t,a):
    if t=="a":
     href=dict(a).get("href"); self.links += [href] if href else []
  if not plan.origin.startswith("file://"): raise PermissionError("offline browser accepts file:// only")
  path=Path(plan.origin[7:]).resolve(); p=P(); p.feed(path.read_text(encoding="utf-8",errors="replace")); return {"text":" ".join(p.text),"links":p.links}
