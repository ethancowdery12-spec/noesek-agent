from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class Envelope:
 channel:str; external_id:str; sender:str; conversation:str; text:str; media:tuple[str,...]=()
 def __post_init__(self):
  if not all((self.channel,self.external_id,self.sender,self.conversation)): raise ValueError("missing envelope identity")
class ChannelAdapter:
 async def normalize(self,payload:dict)->list[Envelope]: raise NotImplementedError
 async def send(self,envelope:Envelope): raise NotImplementedError
