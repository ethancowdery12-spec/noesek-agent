import asyncio
import base64
from types import SimpleNamespace

import pytest

from noesek.tools.screenshot_to_code import (ScreenshotToCodeInput, extract_html, sniff_image,
                                             screenshot_to_code_handler, validate_html)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PAGE = ('<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">'
        "<style>body{color:#111;background:#fff}</style></head><body><h1>Hi</h1></body></html>")


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    from noesek import filestore
    monkeypatch.setattr(filestore, "files_dir", lambda: tmp_path)
    (tmp_path / "shot.png").write_bytes(PNG)
    return tmp_path


class Fake:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    async def complete(self, messages, tools):
        self.seen.append(messages)
        return SimpleNamespace(content=self.replies.pop(0))


def run(llm, **kw):
    async def res():
        return llm
    return asyncio.run(screenshot_to_code_handler(res)(ScreenshotToCodeInput(image_file="shot.png", **kw)))


def test_sniff_and_extract():
    assert sniff_image(PNG) == "image/png" and sniff_image(b"nope") is None
    assert extract_html("x ```html\n" + PAGE + "\n``` y") == PAGE
    assert extract_html("no html here") is None


def test_validate_blocks_unknown_scripts():
    bad = PAGE.replace("<body>", '<body><script src="https://evil.example/x.js"></script>')
    assert any("non-allowlisted" in p for p in validate_html(bad))
    assert validate_html(PAGE) == []


def test_generates_writes_and_picks_best(store):
    worse = PAGE.replace('<meta name="viewport" content="width=device-width">', "")
    llm = Fake(["```html\n" + worse + "\n```", "```html\n" + PAGE + "\n```"])
    out = run(llm, n=2)
    assert [c["file"] for c in out["candidates"]] == ["s2c-1.html", "s2c-2.html"]
    assert out["pick"] == 2
    assert (store / "s2c-2.html").read_text() == PAGE
    sent = llm.seen[0][0]["content"]
    assert sent[1]["image_url"]["url"].startswith("data:image/png;base64," + base64.b64encode(PNG).decode()[:8])


def test_rejects_non_image_and_missing(store):
    (store / "t.png").write_bytes(b"hello")
    async def res(): return Fake([])
    h = screenshot_to_code_handler(res)
    assert "not a PNG" in asyncio.run(h(ScreenshotToCodeInput(image_file="t.png")))["error"]
    assert "error" in asyncio.run(h(ScreenshotToCodeInput(image_file="gone.png")))


def test_model_without_html_reports_error():
    assert "error" in run(Fake(["sorry, cannot see images"]), n=1)
