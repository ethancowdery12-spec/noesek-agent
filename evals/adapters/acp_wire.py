"""Adapter for upstream evals/acp_empty_session_wire.py (Hermes c712f06d).

Upstream intent: drive the ACP stdio wire with a fixture model (never paid
inference), record the wire transcript, and measure empty-session database
state. Noesek target: `python -m noesek.compat.acp_server` with the
NOESEK_ACP_ECHO fixture seam - the Noesek ACP agent serves real stdio JSON-RPC.
"""
import json
import os
import selectors
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, env_for, out_dir


def rpc(proc, sel, transcript, method, params, rid, timeout=180):
    line = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    proc.stdin.write(line + "\n"); proc.stdin.flush()
    transcript.append({"dir": "client->agent", "msg": json.loads(line)})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for key, _ in sel.select(timeout=1):
            raw = proc.stdout.readline()
            if not raw:
                raise RuntimeError("agent closed stdout")
            msg = json.loads(raw)
            transcript.append({"dir": "agent->client", "msg": msg})
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]
    raise TimeoutError(method)


def main():
    out = out_dir()
    home = out / "home"; home.mkdir()
    env = env_for(home, NOESEK_ACP_ECHO="1")
    proc = subprocess.Popen([sys.executable, "-m", "noesek.compat.acp_server"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    sel = selectors.DefaultSelector(); sel.register(proc.stdout, selectors.EVENT_READ)
    transcript = []
    db = home / "noesek.db"
    try:
        init = rpc(proc, sel, transcript, "initialize",
                   {"protocolVersion": 1, "clientCapabilities": {}}, 1)
        assert init["agentInfo"]["name"] == "noesek"
        empty_size = db.stat().st_size if db.exists() else 0
        sess = rpc(proc, sel, transcript, "session/new", {"cwd": "/tmp", "mcpServers": []}, 2)
        resp = rpc(proc, sel, transcript, "session/prompt",
                   {"sessionId": sess["sessionId"],
                    "prompt": [{"type": "text", "text": "ping"}]}, 3)
        assert resp["stopReason"] == "end_turn", resp
    finally:
        proc.kill(); proc.wait()
    (out / "wire-transcript.jsonl").write_text(
        "\n".join(json.dumps(t) for t in transcript) + "\n")
    with sqlite3.connect(db) as conn:
        convs = conn.execute("SELECT COUNT(*) FROM conversations WHERE channel='acp'").fetchone()[0]
    size_after = db.stat().st_size
    ok = convs >= 1 and size_after >= empty_size
    emit("pass" if ok else "fail", conversations=convs,
         db_bytes_empty_session=empty_size, db_bytes_after_prompt=size_after,
         transcript_messages=len(transcript),
         transcript_path=str(out / "wire-transcript.jsonl"))


if __name__ == "__main__":
    main()
