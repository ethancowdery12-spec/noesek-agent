import re
from html.parser import HTMLParser
import httpx
from pydantic import BaseModel, Field
from ..config import settings

class FetchInput(BaseModel):
    url: str = Field(min_length=8, max_length=2000, description="http(s) URL to fetch")
    max_chars: int = Field(default=6000, ge=200, le=20000)

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "template"}
    def __init__(self):
        super().__init__()
        self._skip = 0; self.parts: list[str] = []; self.title = ""; self._in_title = False
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self._skip += 1
        if tag == "title": self._in_title = True
    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip: self._skip -= 1
        if tag == "title": self._in_title = False
    def handle_data(self, data):
        if self._skip: return
        if self._in_title: self.title += data.strip()
        elif data.strip(): self.parts.append(data.strip())

def extract_text(html: str) -> tuple[str, str]:
    """Return (title, readable text) from HTML using only the standard library."""
    p = _TextExtractor(); p.feed(html)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(p.parts))
    return p.title.strip(), text.strip()

async def fetch_url(inp: FetchInput):
    if not inp.url.lower().startswith(("http://", "https://")):
        return {"error": "Only http(s) URLs are supported"}
    headers = {"User-Agent": "noesek-agent/0.2 (+research fetch)", "Accept": "text/html,text/plain,application/json,*/*"}
    try:
        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds, follow_redirects=True, max_redirects=5) as c:
            async with c.stream("GET", inp.url, headers=headers) as r:
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                raw = bytearray()
                async for chunk in r.aiter_bytes(65536):
                    raw += chunk
                    if len(raw) > settings.fetch_max_bytes: break
    except (httpx.HTTPError, ValueError) as e:
        return {"error": f"Fetch failed: {type(e).__name__}", "detail": str(e)[:300]}
    body = bytes(raw).decode(errors="replace")
    if "html" in ctype:
        title, text = extract_text(body)
    else:
        title, text = "", body
    return {"url": inp.url, "content_type": ctype, "title": title, "text": text[:inp.max_chars], "truncated": len(text) > inp.max_chars}
