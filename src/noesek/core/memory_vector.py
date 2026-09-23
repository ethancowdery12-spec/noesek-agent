"""Vector memory (Ethan's vector-memory piece, Sep 21): pluggable embedder with a
zero-dependency local default, vectors stored in SQLite, cosine similarity fused
into recall ranking alongside FTS5 and keyword overlap.

Default embedder is a hashed-ngram vector (hashing trick over token unigrams and
bigrams, signed buckets, L2-normalized): deterministic, no network, no deps. An
OpenAI-compatible /embeddings endpoint can be selected via settings for real
semantic vectors. Storage and search mirror the memory_v2 FTS pattern:
best-effort writes that never break a user turn, feature-detected table.
"""
from __future__ import annotations

import hashlib
import math
import re
from array import array

from sqlalchemy import text

from ..config import settings
from ..db import Session

_TOKEN = re.compile(r"[a-z0-9]{2,}")

_DDL = ("CREATE TABLE IF NOT EXISTS memory_vectors("
        "memory_id INTEGER PRIMARY KEY, conversation_id INTEGER, "
        "dim INTEGER, model TEXT, vector BLOB)")
_table_ok: bool | None = None


def _ngrams(content: str) -> list[str]:
    toks = _TOKEN.findall((content or "").lower())
    return toks + [f"{a} {b}" for a, b in zip(toks, toks[1:])]


class HashedNgramEmbedder:
    """Zero-dep local vectors: hashed token unigrams+bigrams, signed buckets."""
    name = "hashed-ngram"

    def __init__(self, dim: int = 256):
        self.dim = max(32, int(dim))

    def embed(self, content: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _ngrams(content):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0 if (h >> 63) == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


class OpenAICompatibleEmbedder:
    """Real embeddings from any OpenAI-compatible /embeddings endpoint."""
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def embed(self, content: str) -> list[float]:
        import httpx
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds) as c:
            r = await c.post(f"{self.base_url}/embeddings",
                             json={"model": self.model, "input": content[:8000]}, headers=headers)
            r.raise_for_status()
            return [float(x) for x in r.json()["data"][0]["embedding"]]


def get_embedder():
    if settings.embed_provider == "openai-compatible" and settings.embed_base_url and settings.embed_model:
        return OpenAICompatibleEmbedder(settings.embed_base_url, settings.embed_api_key, settings.embed_model)
    return HashedNgramEmbedder(settings.embed_dim)


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


async def embed_text(content: str) -> tuple[list[float], str]:
    emb = get_embedder()
    vec = await _maybe_await(emb.embed(content))
    return vec, emb.name


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if not n: return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n])); nb = math.sqrt(sum(x * x for x in b[:n]))
    return dot / (na * nb) if na and nb else 0.0


async def vectors_available() -> bool:
    global _table_ok
    if _table_ok is None:
        try:
            async with Session() as s:
                await s.execute(text(_DDL)); await s.commit()
            _table_ok = True
        except Exception:
            _table_ok = False
    return _table_ok


async def index_vector(memory_id: int, conversation_id: int, content: str) -> None:
    """Best-effort vector index write; never breaks a user turn."""
    try:
        if not settings.vector_memory_enabled or not await vectors_available(): return
        vec, model = await embed_text(content)
        blob = array("f", vec).tobytes()
        async with Session() as s:
            await s.execute(text("INSERT OR REPLACE INTO memory_vectors(memory_id, conversation_id, dim, model, vector)"
                                 " VALUES (:i, :c, :d, :m, :v)"),
                            {"i": memory_id, "c": conversation_id, "d": len(vec), "m": model, "v": blob})
            await s.commit()
    except Exception:
        pass


async def deindex_vector(memory_id: int) -> None:
    try:
        if not await vectors_available(): return
        async with Session() as s:
            await s.execute(text("DELETE FROM memory_vectors WHERE memory_id = :i"), {"i": memory_id})
            await s.commit()
    except Exception:
        pass


def _unpack(blob: bytes) -> list[float]:
    a = array("f"); a.frombytes(blob)
    return list(a)


async def vector_scores(conversation_id: int | None, query: str, limit: int = 40,
                        pool_conversation_ids: list[int] | None = None) -> dict[int, float]:
    """Cosine similarity per active memory. conversation_id=None scores the
    shared user-wide pool; pool_conversation_ids scopes it explicitly
    (item 68 multi-user seam). Lazily backfills vectors for memories that
    predate the index (bounded batch per call)."""
    if not settings.vector_memory_enabled or not query.strip() or not await vectors_available():
        return {}
    try:
        async with Session() as s:
            sql = ("SELECT m.id, m.content, v.vector FROM memories m "
                   "LEFT JOIN memory_vectors v ON v.memory_id = m.id "
                   "WHERE m.active = 1 ")
            params = {"n": limit}
            if pool_conversation_ids is not None:
                if not pool_conversation_ids: return {}
                sql += "AND m.conversation_id IN :cids "
                params["cids"] = pool_conversation_ids
            elif conversation_id is not None:
                sql += "AND m.conversation_id = :c "
                params["c"] = conversation_id
            sql += "ORDER BY m.created_at DESC LIMIT :n"
            q = text(sql)
            if "cids" in params:
                from sqlalchemy import bindparam
                q = q.bindparams(bindparam("cids", expanding=True))
            rows = (await s.execute(q, params)).all()
        missing = [(mid, content) for mid, content, blob in rows if blob is None]
        for mid, content in missing[:20]:
            await index_vector(mid, conversation_id, content)
        if missing:
            async with Session() as s:
                rows = (await s.execute(text(
                    "SELECT m.id, m.content, v.vector FROM memories m "
                    "LEFT JOIN memory_vectors v ON v.memory_id = m.id "
                    "WHERE m.conversation_id = :c AND m.active = 1 ORDER BY m.created_at DESC LIMIT :n"),
                    {"c": conversation_id, "n": limit})).all()
        qv, _ = await embed_text(query)
        return {mid: cosine(qv, _unpack(blob)) for mid, _, blob in rows if blob is not None}
    except Exception:
        return {}
