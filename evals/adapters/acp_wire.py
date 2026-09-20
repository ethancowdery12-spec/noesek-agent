"""Adapter for upstream evals/acp_empty_session_wire.py (Hermes c712f06d).

Upstream intent: drive the ACP stdio wire with a fixture model (never paid
inference), record the wire transcript, and measure empty-session database
state. Noesek target: `python -m noesek.compat.acp_server` with the
NOESEK_ACP_ECHO fixture seam - the Noesek ACP agent serves real stdio JSON-RPC.

The server's stderr is drained on a daemon thread: the pipe is never read
otherwise, and enough startup logging fills the 64 KiB pipe buffer and blocks
the server mid-startup - the initialize RPC then times out with a live,
silent server process. On any failure the drained stderr tail is emitted for
diagnosis.
"""
import json
import os
import selectors
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, env_for, out_dir


def drain_stderr(proc, sink):
    for line in proc.stderr:
        sink.append(line.rstrip("\n"))


def rpc(proc, sel, transcript, method, params, rid, timeout=180):
    """One JSON-RPC round trip.

    Reads the agent's stdout with os.read on the raw fd, never the buffered
    text wrapper: when the server flushes a session/update notification and
    the final response in one write, a buffered reader coalesces both into
    user space while select() waits on an empty fd - the response sits
    unread and the call times out with a live server (the CI flake seen in
    #42, #57, #64, #65). An explicit byte buffer makes buffered coalescing
    harmless.
    """
    line = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    proc.stdin.write(line + "\n"); proc.stdin.flush()
    transcript.append({"dir": "client->agent", "msg": json.loads(line)})
    fd = proc.stdout.fileno()
    buf = getattr(rpc, "_bufs", {}).get(fd, b"")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if b"\n" not in buf:
            if not sel.select(timeout=1):
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                raise RuntimeError("agent closed stdout")
            buf += chunk
            continue
        raw, buf = buf.split(b"\n", 1)
        if not raw.strip():
            continue
        msg = json.loads(raw.decode())
        transcript.append({"dir": "agent->client", "msg": msg})
        if msg.get("id") == rid:
            _stash_buf(fd, buf)
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg["result"]
    _stash_buf(fd, buf)
    raise TimeoutError(method)


def _stash_buf(fd, buf):
    """Bytes read past the last full line belong to the next rpc call."""
    if not hasattr(rpc, "_bufs"):
        rpc._bufs = {}
    rpc._bufs[fd] = buf


def main():
    out = out_dir()
    home = out / "home"; home.mkdir()
    env = env_for(home, NOESEK_ACP_ECHO="1")
    proc = subprocess.Popen([sys.executable, "-m", "noesek.compat.acp_server"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    stderr_lines = []
    threading.Thread(target=drain_stderr, args=(proc, stderr_lines), daemon=True).start()
    sel = selectors.DefaultSelector(); sel.register(proc.stdout.fileno(), selectors.EVENT_READ)
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
    except Exception as exc:
        proc.kill(); proc.wait()
        emit("error", error=f"{type(exc).__name__}: {exc}",
             stderr_tail=stderr_lines[-40:],
             transcript_messages=len(transcript),
             transcript_path=str(out / "wire-transcript.jsonl"))
        return
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
