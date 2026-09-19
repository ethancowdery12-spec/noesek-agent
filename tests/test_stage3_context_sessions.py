from noesek.core.compression import compact, estimate_chars
from noesek.core.sessions import search_session
from noesek.db import Conversation, Message, Session


def test_compaction_preserves_system_and_latest_turn():
    rows=[{"role":"system","content":"policy"}]+[{"role":"user","content":"x"*200},{"role":"assistant","content":"y"*200}]*5+[{"role":"user","content":"latest"}]
    kept,info=compact(rows,700)
    assert kept[0]["role"]=="system" and kept[-1]["content"]=="latest" and info["removed"]>0
    assert estimate_chars(kept)<=700

def test_compaction_noop_is_stable():
    rows=[{"role":"user","content":"hi"}]; assert compact(rows,256)[0]==rows

async def test_session_search_is_scoped_and_literal(db):
    async with Session() as s:
        a=Conversation(channel="cli",external_user_id="a"); b=Conversation(channel="cli",external_user_id="b"); s.add_all([a,b]); await s.flush()
        s.add_all([Message(conversation_id=a.id,role="user",content="needle 100%"),Message(conversation_id=b.id,role="user",content="needle secret")]); await s.commit(); aid=a.id
    rows=await search_session(aid,"100%")
    assert len(rows)==1 and rows[0]["content"]=="needle 100%"
