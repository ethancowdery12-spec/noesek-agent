from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

class Risk(str, Enum):
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"
    MONEY = "money"
    DESTRUCTIVE = "destructive"

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

class LLMReply(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    # Normalized token usage: {"input_tokens": int|None, "output_tokens": int|None}.
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None

class TurnResult(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)
    pending_approval_id: int | None = None
    # Durable turn spine id (core.turn_spine) for postmortem lookup.
    turn_id: str | None = None
