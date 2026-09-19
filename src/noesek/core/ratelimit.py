import time

class RateLimiter:
    """Fixed-window per-key limiter. In-memory; per-process, which matches a single-instance deployment."""
    def __init__(self, limit: int, window_seconds: float):
        if limit <= 0 or window_seconds <= 0: raise ValueError("limit and window must be positive")
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(hits) >= self.limit:
            self._hits[key] = hits; return False
        hits.append(now); self._hits[key] = hits; return True

    def remaining(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        return max(0, self.limit - len(hits))
