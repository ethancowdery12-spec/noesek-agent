import httpx
from pydantic import BaseModel, Field
from ..config import settings

class SearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    count: int = Field(default=5, ge=1, le=10)

async def search_web(inp: SearchInput):
    if not settings.brave_search_api_key:
        return {"error":"Search is not configured", "setup":"Set NOESEK_BRAVE_SEARCH_API_KEY"}
    headers={"X-Subscription-Token":settings.brave_search_api_key,"Accept":"application/json"}
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.get("https://api.search.brave.com/res/v1/web/search",params={"q":inp.query,"count":inp.count},headers=headers)
        r.raise_for_status(); data=r.json()
    return {"results":[{"title":x.get("title"),"url":x.get("url"),"description":x.get("description")} for x in data.get("web",{}).get("results",[])]}
