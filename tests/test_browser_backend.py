"""Playwright executor behind Noesek's approval-bound plan gate."""
import http.server
import threading
import functools

import pytest

from noesek.core.computer_use import ComputerPlan
from noesek.core.browser_backend import PlaywrightExecutor, execute_approved_plan

PAGE = """<!doctype html><title>t</title>
<input id=q><button id=go onclick="document.title='clicked:'+document.getElementById('q').value">go</button>
<div id=out>hello noesek</div>"""


@pytest.fixture
def local_site(tmp_path):
    handler = functools.partial(_PageHandler)
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


class _PageHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


ALLOWED_ACTIONS = {"navigate", "click", "type", "extract_text", "screenshot"}


def make_plan(origin, actions):
    return ComputerPlan(origin=origin, actions=tuple(actions)).validate(
        allowed_origins={origin}, allowed_actions=ALLOWED_ACTIONS)


async def test_approved_plan_executes_in_real_chromium(local_site):
    plan = make_plan(local_site, [
        {"type": "navigate", "url": local_site + "/"},
        {"type": "extract_text", "selector": "#out"},
        {"type": "type", "selector": "#q", "text": "abc"},
        {"type": "click", "selector": "#go"},
        {"type": "screenshot"},
    ])
    out = await execute_approved_plan(plan, plan.digest)
    assert out["digest"] == plan.digest
    assert out["steps"][1]["text"] == "hello noesek"
    assert out["steps"][3]["selector"] == "#go"
    assert len(out["steps"][4]["png_base64"]) > 1000


async def test_unapproved_digest_refused(local_site):
    plan = make_plan(local_site, [{"type": "navigate", "url": local_site + "/"}])
    with pytest.raises(PermissionError):
        await execute_approved_plan(plan, "0" * 64)


async def test_origin_allowlist_enforced_before_approval(local_site):
    plan = ComputerPlan(origin="https://evil.example", actions=({"type": "navigate", "url": "https://evil.example/"},))
    with pytest.raises(PermissionError):
        plan.validate(allowed_origins={local_site}, allowed_actions=ALLOWED_ACTIONS)


async def test_action_outside_allowlist_rejected(local_site):
    plan = ComputerPlan(origin=local_site, actions=({"type": "navigate", "url": local_site + "/"},))
    with pytest.raises(PermissionError):
        plan.validate(allowed_origins={local_site}, allowed_actions={"extract_text"})
