"""Dependency-free practical terminal UI."""
import asyncio
from .cli import _conversation
from .core.controller import Controller
async def run_tui(user="tui-user",input_fn=input,output_fn=print):
 cid=await _conversation(user); controller=Controller(); output_fn("Noesek TUI. /quit, /pending, /approve ID, /reject ID")
 while True:
  try: text=input_fn("noesek> ").strip()
  except (EOFError,KeyboardInterrupt): break
  if text in {"/quit","/exit"}: break
  if text=="/pending": result=await controller.pending_approvals(cid)
  elif text.startswith("/approve ") or text.startswith("/reject "):
   cmd,raw=text[1:].split(maxsplit=1); result=await controller.decide_approval(cid,int(raw),cmd=="approve")
  else: result=await controller.handle(cid,text)
  output_fn(result.text)
def main(): asyncio.run(run_tui())
