def chunk_text(text: str, limit: int = 4096) -> list[str]:
    """Split a message into channel-safe chunks, preferring paragraph, line, then word boundaries."""
    if not text: return []
    if limit <= 0: raise ValueError("limit must be positive")
    chunks, current = [], ""
    for piece in _pieces(text, limit):
        if len(piece) > limit:
            _flush(chunks, current); current = ""
            piece = piece.strip()
            for i in range(0, len(piece), limit): chunks.append(piece[i:i+limit])
            continue
        if len(current) + len(piece) > limit:
            chunks.append(current.rstrip()); current = piece
        else:
            current += piece
    if current.strip(): chunks.append(current.rstrip())
    return chunks or [""]

def _pieces(text: str, limit: int) -> list[str]:
    out = []
    for para in text.split("\n\n"):
        para = para if para.endswith("\n\n") else para
        if len(para) <= limit:
            out.append(para + "\n\n"); continue
        for line in para.splitlines(keepends=True):
            if len(line) <= limit:
                out.append(line); continue
            buf = ""
            for word in line.split(" "):
                if len(buf) + len(word) + 1 > limit:
                    out.append(buf); buf = word + " "
                else:
                    buf += word + " "
            if buf: out.append(buf)
    return out

def _flush(chunks: list[str], current: str):
    if current.strip(): chunks.append(current.rstrip())
