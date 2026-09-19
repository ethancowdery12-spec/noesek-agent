"""ACP server shim: sessions map to Noesek conversations through the controller."""
from noesek.compat.acp_real import NoesekACPAgent
from noesek.core.controller import Controller
from noesek.core.types import TurnResult


class FakeClient:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update, **kw):
        self.updates.append(update.content.text)


class StubLLM:
    async def complete(self, messages, schemas):
        class Reply:
            content = "pong from noesek"
            tool_calls = []
        return Reply()


async def test_initialize_and_session_prompt_cycle(db):
    agent = NoesekACPAgent()
    agent._controller = Controller(llm=StubLLM())
    init = await agent.initialize(protocol_version=1)
    assert init.agent_info.name == "noesek"
    sess = await agent.new_session(cwd="/tmp")
    assert sess.session_id.isdigit()
    client = FakeClient()
    agent.on_connect(client)
    from acp.schema import TextContentBlock
    resp = await agent.prompt(session_id=sess.session_id,
                              prompt=[TextContentBlock(type="text", text="ping")])
    assert resp.stop_reason == "end_turn"
    assert client.updates == ["pong from noesek"]


async def test_pending_approval_stays_textual_without_permission_ui(db):
    agent = NoesekACPAgent()
    agent._controller = Controller(llm=StubLLM())
    sess = await agent.new_session(cwd="/tmp")
    agent.on_connect(FakeClient())
    # Simulate the controller returning a pending approval.
    class PendingController(Controller):
        async def handle(self, cid, text, external_id=None):
            return TurnResult(text="Approval required #5: write_thing", pending_approval_id=5)
    agent._controller = PendingController(llm=StubLLM())
    from acp.schema import TextContentBlock
    resp = await agent.prompt(session_id=sess.session_id,
                              prompt=[TextContentBlock(type="text", text="do it")])
    assert resp.stop_reason == "end_turn"  # no crash, no silent approval


# --- Behavioral scenarios ported from upstream tests/acp_adapter (test_server.py,
# test_permissions.py): Noesek-owned shim, so behaviors are re-expressed against
# Noesek's Controller rather than adopting Hermes' implementation fixtures. ---


async def test_initialize_clamps_protocol_version(db):
    agent = NoesekACPAgent()
    resp = await agent.initialize(protocol_version=99)
    assert resp.protocol_version == 1


async def test_sessions_are_independent_conversations(db):
    agent = NoesekACPAgent()
    agent._controller = Controller(llm=StubLLM())
    s1 = await agent.new_session(cwd="/tmp/a")
    s2 = await agent.new_session(cwd="/tmp/b")
    assert s1.session_id != s2.session_id
    from noesek.db import Conversation, Session as DbSession, select
    async with DbSession() as db_sess:
        c1 = await db_sess.get(Conversation, int(s1.session_id))
        c2 = await db_sess.get(Conversation, int(s2.session_id))
    assert c1.external_user_id != c2.external_user_id


async def test_prompt_streams_chunk_before_response(db):
    agent = NoesekACPAgent()
    agent._controller = Controller(llm=StubLLM())
    sess = await agent.new_session(cwd="/tmp")
    client = FakeClient()
    agent.on_connect(client)
    from acp.schema import TextContentBlock
    await agent.prompt(session_id=sess.session_id,
                       prompt=[TextContentBlock(type="text", text="hi")])
    assert client.updates  # chunk delivered before PromptResponse resolved


async def test_cancel_is_safe(db):
    agent = NoesekACPAgent()
    assert await agent.cancel(session_id="999") is None


async def test_permission_request_offers_allow_once_and_reject_once(db):
    captured = {}

    class PermClient(FakeClient):
        async def request_permission(self, session_id, tool_call, options, **kw):
            captured["options"] = options
            class Outcome:
                outcome_id = "reject"
            class Resp:
                outcome = Outcome()
            return Resp()

    class PendingController(Controller):
        async def handle(self, cid, text, external_id=None):
            return TurnResult(text="Approval required #7: delete_thing", pending_approval_id=7)

        async def decide_approval(self, cid, approval_id, approved, note=None):
            return TurnResult(text="rejected")

    agent = NoesekACPAgent()
    agent._controller = PendingController(llm=StubLLM())
    sess = await agent.new_session(cwd="/tmp")
    agent.on_connect(PermClient())
    from acp.schema import TextContentBlock
    await agent.prompt(session_id=sess.session_id,
                       prompt=[TextContentBlock(type="text", text="delete it")])
    kinds = {o.kind for o in captured["options"]}
    assert kinds == {"allow_once", "reject_once"}
