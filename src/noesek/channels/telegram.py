from .gateway import Envelope,ChannelAdapter
class TelegramWebhookAdapter(ChannelAdapter):
 async def normalize(self,p):
  m=p.get("message") or p.get("edited_message")
  if not m or not m.get("from") or not m.get("chat"): return []
  return [Envelope("telegram",str(p.get("update_id","")),str(m["from"]["id"]),str(m["chat"]["id"]),m.get("text") or m.get("caption") or "")]
