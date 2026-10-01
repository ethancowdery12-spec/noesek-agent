"""Executable visual-taste checks for generated HTML/CSS ("build in the AI taste").

Own implementation. Taste here means explicit, testable rules chosen per
request - an aesthetic profile - not hidden universal bans. A profile states
what the user picked (for example "gradients allowed", "motion allowed"); the
checker reports findings against that choice, with the exact snippet.
Rule families follow the ideas in the accepted ibelick/ui-skills pass already
condensed in design_system.py (MIT, own words): contrast, hierarchy,
spacing scale, interaction naming, safe motion.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

PROFILES: dict[str, dict] = {
    "restrained": {"gradients": False, "motion": False, "max_fonts": 2,
                   "description": "flat color, no gradients, no decorative motion"},
    "expressive": {"gradients": True, "motion": True, "max_fonts": 3,
                   "description": "gradients and motion allowed, still checked for safety"},
    "neutral": {"gradients": True, "motion": True, "max_fonts": 3,
                "description": "no style opinion; only objective checks run"},
}

_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


class TasteInput(BaseModel):
    html: str = Field(min_length=1, max_length=400_000)
    profile: str = Field(default="neutral", description=f"one of: {', '.join(PROFILES)}")


def _lum(h: str) -> float:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    def ch(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return round((hi + 0.05) / (lo + 0.05), 2)


def _first_color(css: str, prop: str, selector_hint: str) -> str | None:
    m = re.search(selector_hint + r"[^{}]*\{[^}]*?(?<![-\w])" + prop + r"\s*:\s*(#[0-9a-fA-F]{3,6})\b", css, re.S)
    return m.group(1) if m else None


def taste_check(inp: TasteInput) -> dict:
    prof = PROFILES.get(inp.profile.strip().lower())
    if not prof:
        return {"error": f"unknown profile '{inp.profile}'", "profiles": sorted(PROFILES)}
    src = inp.html
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", src, re.S | re.I))
    findings: list[dict] = []

    def add(rule: str, severity: str, detail: str, snippet: str = "") -> None:
        findings.append({"rule": rule, "severity": severity, "detail": detail,
                         "snippet": snippet[:140]})

    # Objective checks (run for every profile).
    if not re.search(r"<meta[^>]+name=[\"']viewport[\"']", src, re.I):
        add("viewport-meta", "error", "missing viewport meta; page will not scale on phones")
    if not re.search(r"<html[^>]+\blang=", src, re.I):
        add("html-lang", "warn", "missing lang attribute on <html>")
    for m in re.finditer(r"<img\b(?![^>]*\balt=)[^>]*>", src, re.I):
        add("img-alt", "error", "image without alt text", m.group(0))
    for m in re.finditer(r"<button\b[^>]*>\s*(?:<(?:svg|i|img)\b[^>]*>.*?</(?:svg|i)>|<img[^>]*>)?\s*</button>", src, re.I | re.S):
        if "aria-label" not in m.group(0).lower():
            add("icon-button-name", "error", "icon-only button has no aria-label", m.group(0))
    if re.search(r"\b100vh\b", css):
        add("fixed-100vh", "warn", "100vh breaks under mobile browser bars; use 100dvh", "100vh")
    for m in re.finditer(r"transition(?:-property)?\s*:\s*[^;]*\b(width|height|top|left|margin|padding)\b[^;]*;", css):
        add("animate-layout", "warn", "animating a layout property; animate transform/opacity", m.group(0))
    if re.search(r"@keyframes|animation\s*:|transition\s*:", css) and "prefers-reduced-motion" not in css:
        add("reduced-motion", "error", "motion without a prefers-reduced-motion fallback")
    fg = _first_color(css, "color", r"(?:body|html|:root)")
    bg = _first_color(css, "background(?:-color)?", r"(?:body|html|:root)")
    if fg and bg:
        ratio = contrast_ratio(fg, bg)
        if ratio < 4.5:
            add("contrast", "error", f"body text contrast {ratio}:1 is under 4.5:1 ({fg} on {bg})")
    sizes = [int(x) for x in re.findall(r"font-size\s*:\s*(\d+)px", css)]
    if sizes and min(sizes) < 12:
        add("tiny-text", "warn", f"font-size {min(sizes)}px is under 12px")
    if len(set(sizes)) > 8:
        add("type-scale", "warn", f"{len(set(sizes))} distinct font sizes; use a short scale")
    # Spacing: flag when most padding/margin px values are off a 4px grid.
    px = [int(x) for x in re.findall(r"(?:padding|margin|gap)[\w-]*\s*:\s*(\d+)px", css)]
    if len(px) >= 6 and sum(1 for v in px if v % 4) / len(px) > 0.4:
        add("spacing-scale", "warn", "over 40% of spacing values are off a 4px grid")
    fonts = {f.strip().strip("'\"").lower() for m in re.findall(r"font-family\s*:\s*([^;}]+)", css)
             for f in m.split(",")[:1]}
    if len(fonts) > prof["max_fonts"]:
        add("font-count", "warn", f"{len(fonts)} primary font families; profile allows {prof['max_fonts']}")

    # Profile (explicit choice) checks.
    if not prof["gradients"] and re.search(r"(?:linear|radial|conic)-gradient\(", css):
        add("profile-gradient", "warn", f"profile '{inp.profile}' chose no gradients")
    if not prof["motion"] and re.search(r"@keyframes|animation\s*:", css):
        add("profile-motion", "warn", f"profile '{inp.profile}' chose no decorative motion")

    errors = sum(1 for f in findings if f["severity"] == "error")
    return {"profile": inp.profile.strip().lower(), "passed": errors == 0,
            "errors": errors, "warnings": len(findings) - errors, "findings": findings}
