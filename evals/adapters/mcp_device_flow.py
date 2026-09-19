"""Adapter for upstream evals/mcp_device_flow.py (Hermes c712f06d).

Upstream intent: a local RFC 8628 device-flow wire fixture (no external
credentials) proving the client drives the device-code grant correctly.
Noesek target: compat.mcp_device_flow.DeviceFlowClient against a local
fixture covering authorization_pending, slow_down (interval +5s per RFC 8628
section 3.5), success with redacted token storage, and expiry termination.
"""
import asyncio
import json
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _common import emit, out_dir


class Fixture(BaseHTTPRequestHandler):
    """RFC 8628 fixture; mode selected by client_id."""

    polls: dict = {}

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        params = dict(p.split("=", 1) for p in body.split("&") if "=" in p)
        mode = params.get("client_id", "ok")
        self.polls[mode] = self.polls.get(mode, 0) + 1
        if self.path == "/device/code":
            expires = 2 if mode == "expiry" else 60
            self.reply({"device_code": f"dc-{mode}", "user_code": "ABCD-EFGH",
                        "verification_uri": "http://127.0.0.1/activate",
                        "expires_in": expires, "interval": 0})
        elif self.path == "/token":
            n = self.polls[mode]
            if mode == "expiry":
                self.reply({"error": "authorization_pending"}, status=400)
            elif n <= 3:  # first token poll
                self.reply({"error": "authorization_pending"}, status=400)
            elif n == 4:
                self.reply({"error": "slow_down"}, status=400)
            else:
                self.reply({"access_token": "fixture-token-" + mode, "token_type": "bearer",
                            "expires_in": 3600, "scope": "mcp"})
        else:
            self.reply({"error": "not_found"}, status=404)

    def reply(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


async def drive(port, mode, store, home):
    from noesek.compat.mcp_device_flow import (DeviceFlowClient,
                                               DeviceFlowConfig)
    cfg = DeviceFlowConfig(device_authorization_url=f"http://127.0.0.1:{port}/device/code",
                           token_url=f"http://127.0.0.1:{port}/token",
                           client_id=mode, scopes=["mcp"])
    flow = DeviceFlowClient(cfg, store)
    user = await flow.begin()
    assert user["user_code"] == "ABCD-EFGH" and "device_code" not in user
    return await flow.complete(f"ref-{mode}")


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    import os
    os.environ["NOESEK_HOME"] = str(home)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    from noesek.compat.mcp_device_flow import DeviceFlowError, FileTokenStore
    store = FileTokenStore(home / "tokens")

    details = {}
    status = asyncio.run(drive(port, "ok", store, home))
    details["flow_completed"] = status["present"] and status["token_type"] == "bearer"
    details["status_redacted"] = (status["access_token"].startswith("sha256:")
                                  and "fixture-token" not in json.dumps(status))
    stored = store.get("ref-ok")
    details["token_stored"] = stored is not None and stored["access_token"] == "fixture-token-ok"
    tf = home / "tokens" / "ref-ok.json"
    details["file_perms_600"] = oct(tf.stat().st_mode & 0o777) == "0o600"
    details["slow_down_seen"] = Fixture.polls["ok"] >= 5  # pending, slow_down, then success

    try:
        asyncio.run(drive(port, "expiry", store, home))
        details["expiry_terminates"] = False
    except DeviceFlowError as e:
        details["expiry_terminates"] = "expired_token" in str(e)
        details["expiry_message_clean"] = "dc-" not in str(e)  # no device code in errors
    server.shutdown()

    ok = all(v for k, v in details.items() if isinstance(v, bool))
    emit("pass" if ok else "fail", **details)


if __name__ == "__main__":
    main()
