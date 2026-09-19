"""Adapter for upstream evals/gateway/session_time_persistence_*.py (Hermes c712f06d).

Upstream intent: session timestamps persisted to disk must survive a process
restart byte-for-byte. Noesek target: conversations/messages in the sqlite
store, written by one process and read back by a fresh one.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, env_for, out_dir

WRITE = """
import asyncio
from noesek.db import init_db, Session
from noesek.db import Conversation, Message
async def go():
    await init_db()
    async with Session() as s:
        c = Conversation(channel="telegram", external_user_id="u-1")
        s.add(c); await s.flush()
        s.add(Message(conversation_id=c.id, role="user", content="hello"))
        await s.commit()
asyncio.run(go())
"""
READ = """
import asyncio, json
from sqlalchemy import select
from noesek.db import init_db, Session
from noesek.db import Conversation, Message
async def go():
    await init_db()
    async with Session() as s:
        convs = (await s.execute(select(Conversation))).scalars().all()
        msgs = (await s.execute(select(Message))).scalars().all()
        print(json.dumps({
            "conversations": [(c.id, c.channel, c.external_user_id, c.created_at.isoformat()) for c in convs],
            "messages": [(m.id, m.conversation_id, m.role, m.created_at.isoformat()) for m in msgs]}))
asyncio.run(go())
"""


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    rw = subprocess.run([sys.executable, "-c", WRITE], env=env_for(home),
                        capture_output=True, text=True, timeout=60)
    assert rw.returncode == 0, rw.stderr
    rr = subprocess.run([sys.executable, "-c", READ], env=env_for(home),
                        capture_output=True, text=True, timeout=60)
    assert rr.returncode == 0, rr.stderr
    first = json.loads(rr.stdout)
    # second fresh process reads the same file: values must be identical
    rr2 = subprocess.run([sys.executable, "-c", READ], env=env_for(home),
                         capture_output=True, text=True, timeout=60)
    second = json.loads(rr2.stdout)
    ok = (first == second and len(first["conversations"]) == 1
          and len(first["messages"]) == 1
          and all(ts for *_ , ts in first["conversations"] + first["messages"]))
    emit("pass" if ok else "fail", conversations=len(first["conversations"]),
         messages=len(first["messages"]), stable_across_processes=first == second,
         sample_created_at=first["conversations"][0][3] if first["conversations"] else None)


if __name__ == "__main__":
    main()
