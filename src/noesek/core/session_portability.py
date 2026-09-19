"""Validated session export/import format. Import never overwrites a session."""
from pydantic import BaseModel,Field
from typing import Literal
from sqlalchemy import select
from ..db import Conversation,Message,Session,get_or_create_conversation
class PortableMessage(BaseModel):
    role:Literal["user","assistant","system"]; content:str=Field(max_length=1_000_000)
class PortableSession(BaseModel):
    format:Literal["noesek-session-v1"]="noesek-session-v1"; messages:list[PortableMessage]=Field(max_length=10000)
async def import_session(payload:dict,channel:str,external_user_id:str)->int:
    data=PortableSession.model_validate(payload)
    async with Session() as s:
        existing=(await s.execute(select(Conversation).where(Conversation.channel==channel,Conversation.external_user_id==external_user_id))).scalar_one_or_none()
        if existing: raise ValueError("destination session already exists")
        conv=await get_or_create_conversation(s,channel,external_user_id)
        s.add_all([Message(conversation_id=conv.id,role=m.role,content=m.content) for m in data.messages]); await s.commit(); return conv.id
async def resume_session(channel:str,external_user_id:str)->int:
    async with Session() as s:
        row=(await s.execute(select(Conversation).where(Conversation.channel==channel,Conversation.external_user_id==external_user_id))).scalar_one_or_none()
        if not row: raise LookupError("session not found")
        return row.id
