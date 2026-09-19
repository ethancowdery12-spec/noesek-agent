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

class TurnResult(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)
    pending_approval_id: int | None = None
