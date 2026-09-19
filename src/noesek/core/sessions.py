from sqlalchemy import select
from ..db import Message, Session

async def search_session(conversation_id: int, query: str, limit: int=20) -> list[dict]:
    if not query.strip(): raise ValueError("query is required")
    pattern=f"%{query.replace('%','\\%').replace('_','\\_')}%"
    async with Session() as s:
        rows=(await s.execute(select(Message).where(Message.conversation_id==conversation_id,Message.content.ilike(pattern,escape="\\")).order_by(Message.created_at.desc()).limit(limit))).scalars().all()
    return [{"id":m.id,"role":m.role,"content":m.content,"created_at":m.created_at.isoformat()} for m in rows]
