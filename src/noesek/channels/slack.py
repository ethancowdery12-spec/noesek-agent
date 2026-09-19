from .gateway import Envelope,ChannelAdapter
class SlackEventsAdapter(ChannelAdapter):
 async def normalize(self,p):
  if p.get("type")=="url_verification": return []
  e=p.get("event",{})
  if e.get("type")!="message" or e.get("subtype") or not e.get("user"): return []
  return [Envelope("slack",p.get("event_id",""),e["user"],e.get("channel",""),e.get("text",""))]
