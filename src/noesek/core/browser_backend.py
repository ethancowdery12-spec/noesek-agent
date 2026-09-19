"""Playwright browser executor for Noesek approval-bound computer-use plans.

The plan/digest/allowlist contract lives in noesek.core.computer_use: a plan is
validated against origin and action allowlists, its digest is what the operator
approves, and execution refuses any plan whose digest differs. This module is
only the executor: it runs an approved plan in a headless Chromium subprocess
managed by the pinned Playwright library (Apache-2.0). Playwright owns the
browser process boundary; Noesek owns policy.
"""
from __future__ import annotations

import base64
from typing import Any

EXECUTABLE_ACTIONS = frozenset({"navigate", "click", "type", "extract_text", "screenshot"})


class BrowserBackendError(RuntimeError):
    pass


class PlaywrightExecutor:
    """Executes an approved ComputerPlan in headless Chromium.

    Action vocabulary (all validated upstream by ComputerPlan.validate):
      navigate      {type, url}              - must stay inside the plan origin
      click         {type, selector}
      type          {type, selector, text}
      extract_text  {type, selector}         - captured into results
      screenshot    {type, path?}            - PNG bytes, base64, into results
    """

    def __init__(self, *, timeout_ms: float = 30_000, headless: bool = True):
        self.timeout_ms = timeout_ms
        self.headless = headless

    async def run(self, plan) -> dict[str, Any]:
        from playwright.async_api import async_playwright
        results: list[dict[str, Any]] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            try:
                page = await browser.new_page()
                page.set_default_timeout(self.timeout_ms)
                for i, action in enumerate(plan.actions):
                    results.append(await self._step(page, action, i))
            finally:
                await browser.close()
        return {"origin": plan.origin, "digest": plan.digest, "steps": results}

    async def _step(self, page, action: dict, index: int) -> dict[str, Any]:
        kind = action.get("type")
        if kind == "navigate":
            url = str(action.get("url", ""))
            if not url.startswith(("http://", "https://")):
                raise BrowserBackendError(f"step {index}: navigate requires an http(s) URL")
            await page.goto(url)
            return {"step": index, "type": kind, "url": page.url, "title": await page.title()}
        if kind == "click":
            await page.click(str(action["selector"]))
            return {"step": index, "type": kind, "selector": action["selector"]}
        if kind == "type":
            await page.fill(str(action["selector"]), str(action.get("text", "")))
            return {"step": index, "type": kind, "selector": action["selector"]}
        if kind == "extract_text":
            text = await page.locator(str(action["selector"])).inner_text()
            return {"step": index, "type": kind, "selector": action["selector"], "text": text}
        if kind == "screenshot":
            png = await page.screenshot()
            return {"step": index, "type": kind, "png_base64": base64.b64encode(png).decode()}
        raise BrowserBackendError(f"step {index}: unsupported action {kind!r}")


async def execute_approved_plan(plan, approved_digest: str, *, executor=None) -> dict[str, Any]:
    """Policy gate + execution: refuses any plan whose digest was not approved."""
    from .computer_use import execute_plan
    return await execute_plan(plan, approved_digest, executor or PlaywrightExecutor())
