import asyncio
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
    def __init__(self): self._tools: dict[str, ToolSpec] = {}
    def register(self, spec: ToolSpec):
        if spec.name in self._tools: raise ValueError(f"duplicate tool: {spec.name}")
        self._tools[spec.name] = spec
    def get(self, name: str) -> ToolSpec: return self._tools[name]
    def names(self) -> list[str]: return list(self._tools)
    def search(self, query: str, limit: int = 5) -> list[str]:
        """Rank tool names by keyword: exact > name-substring > description-substring."""
        q = query.strip().lower()
        if not q:
            return []
        scored = []
        for t in self._tools.values():
            name, desc = t.name.lower(), (t.description or "").lower()
            score = 3 if name == q else 2 if q in name else 1 if q in desc else 0
            if score:
                scored.append((score, t.name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [n for _, n in scored[:limit]]

    def schemas(self) -> list[dict]:
        return [{"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.input_model.model_json_schema()}} for t in self._tools.values()]
    async def invoke(self, name: str, arguments: dict):
        spec = self.get(name)
        parsed = spec.input_model.model_validate(arguments)
        async with spec._semaphore:
            try:
                return await asyncio.wait_for(spec.handler(parsed), timeout=spec.timeout_seconds)
            except TimeoutError as e:
                raise ToolTimeoutError(f"tool {name} timed out after {spec.timeout_seconds}s") from e
