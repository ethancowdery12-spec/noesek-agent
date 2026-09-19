"""ACP stdio server: an SDK client speaks to the Noesek agent subprocess over real pipes."""
import os
import sys

import pytest


async def test_acp_roundtrip_over_stdio(db, monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/acp.db")
    import acp
    from acp.schema import TextContentBlock

    class ProbeClient:
        def __init__(self):
            self.updates = []

        async def session_update(self, session_id, update, **kw):
            text = getattr(getattr(update, "content", None), "text", None)
            if text:
                self.updates.append(text)

    env = {**os.environ, "PYTHONPATH": os.path.abspath("src"),
           "NOESEK_DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/acp.db",
           "NOESEK_HOME": str(tmp_path), "NOESEK_ACP_ECHO": "1"}
    client = ProbeClient()
    async with acp.spawn_agent_process(
            client, sys.executable, "-m", "noesek.compat.acp_server", env=env) as (conn, proc):
        init = await conn.initialize(protocol_version=1)
        assert init.agent_info.name == "noesek"
        sess = await conn.new_session(cwd="/tmp", mcp_servers=[])
        resp = await conn.prompt(session_id=sess.session_id,
                                 prompt=[TextContentBlock(type="text", text="ping")])
        assert resp.stop_reason == "end_turn"
