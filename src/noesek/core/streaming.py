"""Strict SSE parser used by provider adapters; caps buffered event size."""
def parse_sse(chunks, max_event_bytes: int=1_000_000):
    buf=""
    for chunk in chunks:
        buf += chunk.decode("utf-8",errors="replace") if isinstance(chunk,bytes) else chunk
        if len(buf.encode())>max_event_bytes: raise ValueError("SSE event exceeds limit")
        while "\n\n" in buf:
            raw,buf=buf.split("\n\n",1); data=[]
            for line in raw.splitlines():
                if line.startswith("data:"): data.append(line[5:].lstrip())
            if data: yield "\n".join(data)
