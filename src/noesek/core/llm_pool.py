"""Bounded concurrency for LLM calls (auxiliary resource governance).

Prevents background work from starving interactive replies. Default is
unbounded (limit 0) so single-provider behavior is unchanged unless the
operator opts in via NOESEK_LLM_MAX_CONCURRENT.
"""
from __future__ import annotations

import asyncio


class LLMPool:
    def __init__(self, max_concurrent: int = 0):
        self.limit = max_concurrent
        self._sem = asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None
        self.started = 0
        self.waited = 0

    async def __aenter__(self):
        if self._sem is None:
            self.started += 1
            return self
        if self._sem.locked():
            self.waited += 1
        await self._sem.acquire()
        self.started += 1
        return self

    async def __aexit__(self, *exc):
        if self._sem is not None:
            self._sem.release()

    def stats(self) -> dict:
        return {"limit": self.limit, "started": self.started, "waited": self.waited}


_pool: LLMPool | None = None


def get_pool() -> LLMPool:
    global _pool
    if _pool is None:
        from ..config import settings
        _pool = LLMPool(settings.llm_max_concurrent)
    return _pool
