"""ACP (Agent Client Protocol) server shim over the pinned agent-client-protocol SDK.

Noesek is the single orchestrator: each ACP session maps to a Noesek
conversation handled by the Noesek Controller, so every approval gate, risk
class, and audit trace applies unchanged. When a turn ends in a pending
approval, the shim surfaces it through ACP requestPermission when the client
supports it, and as plain session text otherwise.
"""
from __future__ import annotations

import asyncio
from typing import Any

from acp import Agent, Client
from acp.schema import (AgentMessageChunk, Implementation, InitializeResponse,
                        NewSessionResponse, PromptResponse, TextContentBlock)

ACP_PROTOCOL_VERSION = 1


def _prompt_text(blocks: list) -> str:
    parts = []
    for b in blocks or []:
        text = getattr(b, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


class NoesekACPAgent(Agent):
    def __init__(self, controller=None):
        self._controller = controller
        self._conn: Client | None = None

    def _make_controller(self):
        if self._controller is not None:
            return self._controller
        from ..core.controller import Controller
        self._controller = Controller()
        return self._controller

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(self, protocol_version: int, client_capabilities=None,
                         client_info=None, **kw: Any) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=min(protocol_version, ACP_PROTOCOL_VERSION),
            agent_info=Implementation(name="noesek", title="Noesek Agent", version="1.4.0"),
        )

    async def new_session(self, cwd: str, additional_directories=None,
                          mcp_servers=None, **kw: Any) -> NewSessionResponse:
        from ..db import Conversation, Session
        async with Session() as s:
            c = Conversation(channel="acp", external_user_id=f"acp:{cwd or '.'}")
            s.add(c); await s.commit()
            return NewSessionResponse(session_id=str(c.id))

    async def prompt(self, session_id: str, prompt: list, **kw: Any) -> PromptResponse:
        controller = self._make_controller()
        text = _prompt_text(prompt)
        if not text.strip():
            return PromptResponse(stop_reason="end_turn")
        result = await controller.handle(int(session_id), text)
        reply = result.text or ""
        if self._conn is not None and reply:
            await self._conn.session_update(
                session_id=session_id,
                update=AgentMessageChunk(session_update="agent_message_chunk", content=TextContentBlock(type="text", text=reply)))
        if result.pending_approval_id is not None:
            await self._surface_approval(session_id, result)
        return PromptResponse(stop_reason="end_turn")

    async def _surface_approval(self, session_id: str, result) -> None:
        if self._conn is None:
            return
        try:
            from acp.schema import (PermissionOption,
                                    RequestPermissionRequest,
                                    ToolCallStart)
            options = [
                PermissionOption(kind="allow_once", name="Approve", option_id="approve"),
                PermissionOption(kind="reject_once", name="Reject", option_id="reject"),
            ]
            tc = ToolCallStart(session_update="tool_call", session_id=session_id, tool_call_id=f"approval-{result.pending_approval_id}",
                               title=result.text[:120], kind="other")
            response = await self._conn.request_permission(session_id=session_id, tool_call=tc, options=options)
            outcome = getattr(response, "outcome", None)
            selected = getattr(outcome, "option_id", None) or getattr(outcome, "outcome_id", None)
            if selected:
                approved = str(selected) == "approve"
                followup = await self._make_controller().decide_approval(
                    int(session_id), int(result.pending_approval_id), approved)
                if followup.text:
                    await self._conn.session_update(
                        session_id=session_id,
                        update=AgentMessageChunk(session_update="agent_message_chunk", content=TextContentBlock(type="text", text=followup.text)))
        except Exception:
            # Clients without permission UI keep the in-chat approve/reject flow.
            pass

    async def cancel(self, session_id: str, **kw: Any) -> None:
        return None
