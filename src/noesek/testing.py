"""Deterministic LLM double for tests and golden evaluations."""
from .core.types import LLMReply, ToolCall

class ScriptedLLM:
    """Plays back a fixed script of replies and records every request it receives."""
    def __init__(self, script: list[LLMReply]):
        self.script = list(script); self.requests: list[dict] = []

    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.script: raise AssertionError("ScriptedLLM script exhausted")
        return self.script.pop(0)

def text_reply(content: str) -> LLMReply:
    return LLMReply(content=content)

def tool_reply(name: str, arguments: dict, call_id: str = "call-1", content: str | None = None) -> LLMReply:
    return LLMReply(content=content, tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)])
