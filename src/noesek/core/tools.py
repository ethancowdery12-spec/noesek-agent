import asyncio, inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from pydantic import BaseModel
from .types import Risk

Handler = Callable[[BaseModel], Awaitable[Any]]

class ToolTimeoutError(TimeoutError): pass

@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    risk: Risk
    handler: Handler
    timeout_seconds: float = 45.0
    concurrency: int = 4
    _semaphore: asyncio.Semaphore = field(init=False, repr=False)
    def __post_init__(self):
        if self.timeout_seconds <= 0: raise ValueError("timeout_seconds must be positive")
        if self.concurrency <= 0: raise ValueError("concurrency must be positive")
        self._semaphore = asyncio.Semaphore(self.concurrency)

class ToolRegistry:
    def __init__(self): self._tools: dict[str, ToolSpec] = {}; self._deferred: set[str] = set(); self._ranker = None
    def register(self, spec: ToolSpec):
        if spec.name in self._tools: raise ValueError(f"duplicate tool: {spec.name}")
        self._tools[spec.name] = spec
        self._ranker = None
    # Deferred schema exposure (v2, stage F): deferred tools stay searchable but
    # their schemas stay out of the prompt until activated (search-then-activate).
    def defer(self, name: str):
        self.get(name); self._deferred.add(name)
    def activate(self, name: str):
        self.get(name); self._deferred.discard(name)
    def deferred_names(self) -> list[str]: return sorted(self._deferred)
    def get(self, name: str) -> ToolSpec: return self._tools[name]
    def names(self) -> list[str]: return list(self._tools)
    def search(self, query: str, limit: int = 5) -> list[str]:
        """Rank tools by BM25 over name + description tokens (roadmap item 82).

        Replaces the original keyword-substring tiers, which scored 0-2%
        top-5 on the frozen natural-language acceptance fixtures vs BM25's
        100% (evals/tool_retrieval.py). Only positive-score hits return."""
        q = query.strip().lower()
        if not q:
            return []
        if q in self._tools:
            return [q]  # exact name lookup short-circuits ranking
        if self._ranker is None:
            from .tool_rank import BM25, tokenize
            names = list(self._tools)
            docs = [tokenize(n) * 2 + tokenize(self._tools[n].description or "") for n in names]
            self._ranker = (names, BM25(docs))
        names, bm25 = self._ranker
        return [names[i] for score, i in bm25.rank(query, limit) if score > 0]

    def schemas(self) -> list[dict]:
        return [{"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.input_model.model_json_schema()}} for t in self._tools.values() if t.name not in self._deferred]
    async def invoke(self, name: str, arguments: dict):
        spec = self.get(name)
        parsed = spec.input_model.model_validate(arguments)
        async with spec._semaphore:
            try:
                # Handlers may be sync or async (design_system/office_doc/
                # playbooks are sync): awaiting a plain dict raises TypeError.
                result = spec.handler(parsed)
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(result, timeout=spec.timeout_seconds)
                return result
            except TimeoutError as e:
                raise ToolTimeoutError(f"tool {name} timed out after {spec.timeout_seconds}s") from e
