"""ACP stdio server entrypoint: serve the Noesek ACP agent over stdin/stdout.

Lets any ACP client (editors, upstream wire probes, the acp SDK's own
connect_to_agent) attach to Noesek as a standard ACP subprocess. Sessions map
to Noesek conversations; the Noesek Controller remains the orchestrator.
"""
from __future__ import annotations

import asyncio

from .acp_real import NoesekACPAgent


async def serve() -> None:
    import os
    from acp import run_agent
    from ..db import init_db
    await init_db()

    controller = None
    if os.environ.get("NOESEK_ACP_ECHO"):
        from ..core.controller import Controller

        class _EchoLLM:
            """Test seam: echo the last user message; no network, no keys."""

            async def complete(self, messages, schemas):
                class Reply:
                    content = "echo: " + str(messages[-1].get("content", ""))
                    tool_calls = []
                return Reply()

        controller = Controller(llm=_EchoLLM())
    await run_agent(NoesekACPAgent(controller=controller))


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
