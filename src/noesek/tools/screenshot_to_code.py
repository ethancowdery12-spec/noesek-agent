"""Screenshot-to-code (owner-requested build, abi/screenshot-to-code idea).

Upstream abi/screenshot-to-code is MIT (license verified on disk in the
vendor audit); this is an own implementation of the idea, no upstream code
copied: send a screenshot to a vision-capable model with a strict "output one
self-contained HTML file" prompt, generate N candidates in parallel with
different fidelity lenses, validate each, run the taste checks, write every
candidate to the file store and recommend the best by objective findings.

Safety/cost: the only model calls go through the chat's resolved adapter, so
spend is whatever that chat's model already costs. Input is bounded (5 MB,
PNG/JPEG/WebP/GIF by magic bytes). Generated code must pass a structural
validation and never ships remote scripts other than an allowlist of CDNs.
"""
from __future__ import annotations

import asyncio
import base64
import re

from pydantic import BaseModel, Field

from .. import filestore
from .taste_check import PROFILES, TasteInput, taste_check

MAX_IMAGE_BYTES = 5 * 1024 * 1024
STACKS = {
    "html_css": "plain HTML with one <style> block, no frameworks, no JavaScript unless the screenshot needs interaction",
    "html_tailwind": "HTML using Tailwind via https://cdn.tailwindcss.com, no other scripts unless needed",
}
LENSES = {
    "faithful": "Match the screenshot as exactly as you can: layout, spacing, colors, text.",
    "clean": "Keep the layout and content, but use a tidy spacing scale, semantic tags and sensible type sizes.",
    "responsive": "Keep the look, but make it fully responsive from 360px to desktop widths.",
}
ALLOWED_SCRIPT_HOSTS = ("cdn.tailwindcss.com", "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com")

_MAGIC = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
          (b"GIF8", "image/gif"))


class ScreenshotToCodeInput(BaseModel):
    image_file: str = Field(description="screenshot file name in the agent file store")
    stack: str = Field(default="html_css", description=f"one of: {', '.join(STACKS)}")
    n: int = Field(default=2, ge=1, le=3, description="candidates to generate (1-3)")
    instructions: str = Field(default="", max_length=1500, description="extra changes to apply")
    profile: str = Field(default="neutral", description=f"taste profile: {', '.join(PROFILES)}")
    output_prefix: str = Field(default="s2c", max_length=40, pattern=r"^[A-Za-z0-9_-]+$")


def sniff_image(data: bytes) -> str | None:
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def extract_html(text: str) -> str | None:
    m = re.search(r"```(?:html)?\s*\n(.*?)```", text, re.S | re.I)
    body = (m.group(1) if m else text).strip()
    i = body.lower().find("<!doctype")
    if i < 0:
        i = body.lower().find("<html")
    if i < 0:
        return None
    body = body[i:]
    j = body.lower().rfind("</html>")
    return body[: j + 7] if j >= 0 else None


def validate_html(html: str) -> list[str]:
    problems = []
    low = html.lower()
    for tag in ("<html", "<head", "<body"):
        if tag not in low:
            problems.append(f"missing {tag}>")
    for m in re.finditer(r"<script[^>]+src=[\"']([^\"']+)", html, re.I):
        url = m.group(1)
        host = re.sub(r"^https?://", "", url).split("/")[0]
        if not url.startswith("http") or host not in ALLOWED_SCRIPT_HOSTS:
            problems.append(f"script from non-allowlisted source: {url[:80]}")
    if re.search(r"\bon\w+\s*=\s*[\"'][^\"']*(?:document\.cookie|localStorage|fetch\()", html, re.I):
        problems.append("inline handler touches cookies/storage/network")
    return problems


def _prompt(inp: ScreenshotToCodeInput, lens: str) -> str:
    p = (f"You turn a screenshot into one self-contained web page. Use {STACKS[inp.stack]}. "
         f"{LENSES[lens]} Use placeholder images from https://placehold.co only where the "
         "screenshot has photos; never invent brand logos. Reply with exactly one ```html code "
         "block containing the full document and nothing else.")
    if inp.instructions.strip():
        p += f"\nApply these changes: {inp.instructions.strip()}"
    return p


def screenshot_to_code_handler(llm_resolver):
    async def h(inp: ScreenshotToCodeInput):
        if inp.stack not in STACKS:
            return {"error": f"unknown stack '{inp.stack}'", "stacks": sorted(STACKS)}
        if inp.profile.strip().lower() not in PROFILES:
            return {"error": f"unknown profile '{inp.profile}'", "profiles": sorted(PROFILES)}
        try:
            data = filestore.read_file(inp.image_file)
        except filestore.FileStoreError as exc:
            return {"error": str(exc)}
        if len(data) > MAX_IMAGE_BYTES:
            return {"error": f"image exceeds {MAX_IMAGE_BYTES} bytes"}
        mime = sniff_image(data)
        if not mime:
            return {"error": "not a PNG, JPEG, GIF or WebP image"}
        url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        lenses = list(LENSES)[: inp.n]

        async def one(lens: str):
            try:
                llm = await llm_resolver()
                reply = await llm.complete([{"role": "user", "content": [
                    {"type": "text", "text": _prompt(inp, lens)},
                    {"type": "image_url", "image_url": {"url": url}}]}], [])
                return extract_html(reply.content or "")
            except Exception:
                return None

        results = await asyncio.gather(*(one(l) for l in lenses))
        cands = []
        for lens, html in zip(lenses, results):
            if not html:
                continue
            problems = validate_html(html)
            taste = taste_check(TasteInput(html=html, profile=inp.profile))
            n = len(cands) + 1
            name = f"{inp.output_prefix}-{n}.html"
            try:
                filestore.write_file(name, html)
            except filestore.FileStoreError as exc:
                return {"error": str(exc)}
            cands.append({"n": n, "lens": lens, "file": name, "download": f"/files/{name}",
                          "validation_problems": problems, "taste_errors": taste["errors"],
                          "taste_warnings": taste["warnings"], "taste": taste["findings"][:8]})
        if not cands:
            return {"error": "no candidate produced valid HTML; the chat model may not accept images"}
        best = min(cands, key=lambda c: (len(c["validation_problems"]), c["taste_errors"],
                                         c["taste_warnings"], c["n"]))
        return {"candidates": cands, "pick": best["n"],
                "reason": "fewest validation problems, then taste errors, then warnings",
                "note": "visual match to the screenshot is not machine-checked; open the files"}
    return h
