"""Design-system skills inside the agent (roadmap item 54).

Open-design's core idea (nexu-io/open-design, Apache-2.0 - pattern studied,
no assets copied): a design system is a schema'd package - tokens (color,
type, spacing, radius) plus template guidance - not loose markdown. This tool
ships that as agent capability: a small set of own-value themes in token
schema, and templates that render self-contained HTML deliverables into the
agent file store (downloadable via /files). The agent answers "make it look
good" with a real system instead of ad-hoc styling.
"""
from __future__ import annotations

import html

from pydantic import BaseModel, Field

from .. import filestore

# Schema: colors {bg, surface, ink, muted, accent}, font stack, type scale (px),
# spacing scale (px), corner radius (px). Values are our own.
THEMES: dict[str, dict] = {
    "ink": {
        "description": "dark, modern, high contrast",
        "colors": {"bg": "#101014", "surface": "#1a1a22", "ink": "#f2f2f5",
                   "muted": "#9a9aa8", "accent": "#6ea8fe"},
        "font": "'Segoe UI', system-ui, sans-serif",
        "scale": {"h1": 40, "h2": 26, "body": 17},
        "spacing": {"unit": 8, "page": 56},
        "radius": 14,
    },
    "paper": {
        "description": "light, editorial, serif headings",
        "colors": {"bg": "#faf8f4", "surface": "#ffffff", "ink": "#22201c",
                   "muted": "#6f6a60", "accent": "#9a4b1f"},
        "font": "Georgia, 'Times New Roman', serif",
        "scale": {"h1": 38, "h2": 24, "body": 17},
        "spacing": {"unit": 8, "page": 64},
        "radius": 4,
    },
    "signal": {
        "description": "light, bold accent, startup energy",
        "colors": {"bg": "#ffffff", "surface": "#f4f6fb", "ink": "#131a2a",
                   "muted": "#5b6478", "accent": "#2f5cff"},
        "font": "'Segoe UI', system-ui, sans-serif",
        "scale": {"h1": 42, "h2": 26, "body": 17},
        "spacing": {"unit": 8, "page": 56},
        "radius": 10,
    },
}

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title><style>
:root {{ --bg: {bg}; --surface: {surface}; --ink: {ink}; --muted: {muted}; --accent: {accent}; }}
body {{ background: var(--bg); color: var(--ink); font-family: {font}; font-size: {body}px;
       margin: 0 auto; max-width: 780px; padding: {page}px 24px; line-height: 1.6; }}
h1 {{ font-size: {h1}px; line-height: 1.15; margin: 0 0 8px; }}
.subtitle {{ color: var(--muted); font-size: {h2}px; margin: 0 0 {page}px; }}
section {{ background: var(--surface); border-radius: {radius}px; padding: 24px 28px; margin: 0 0 24px; }}
h2 {{ font-size: {h2}px; margin: 0 0 8px; color: var(--accent); }}
footer {{ color: var(--muted); font-size: 14px; margin-top: {page}px; }}
</style></head><body>
<h1>{title}</h1>{subtitle}
{sections}
<footer>Made with noesek design_system - theme '{theme}'</footer>
</body></html>"""


class DesignInput(BaseModel):
    action: str = Field(description="list | get | render")
    theme: str = Field(default="ink", description=f"one of: {', '.join(THEMES)}")
    title: str = Field(default="Untitled", max_length=120)
    subtitle: str = Field(default="", max_length=200)
    sections: list[str] = Field(default_factory=list, max_length=20,
                                description="render: 'Heading | body text' entries")
    file_name: str = Field(default="page.html", description="render: output name in the file store")


def _tokens(theme: str) -> dict | None:
    return THEMES.get(theme.strip().lower())


def design_system(inp: DesignInput) -> dict:
    action = inp.action.strip().lower()
    if action == "list":
        return {"themes": {k: v["description"] for k, v in THEMES.items()}}
    t = _tokens(inp.theme)
    if not t:
        return {"error": f"unknown theme '{inp.theme}'", "themes": sorted(THEMES)}
    if action == "get":
        return {"theme": inp.theme.strip().lower(), "tokens": t}
    if action == "render":
        if not inp.file_name.lower().endswith(".html"):
            return {"error": "file_name must end in .html"}
        secs = []
        for s in inp.sections:
            heading, _, body = s.partition("|")
            secs.append(f"<section><h2>{html.escape(heading.strip())}</h2>"
                        f"<p>{html.escape(body.strip())}</p></section>")
        sub = f'<p class="subtitle">{html.escape(inp.subtitle)}</p>' if inp.subtitle.strip() else ""
        c, sc, sp = t["colors"], t["scale"], t["spacing"]
        page = _PAGE.format(title=html.escape(inp.title), subtitle=sub,
                            sections="\n".join(secs), theme=inp.theme.strip().lower(),
                            bg=c["bg"], surface=c["surface"], ink=c["ink"], muted=c["muted"],
                            accent=c["accent"], font=t["font"],
                            h1=sc["h1"], h2=sc["h2"], body=sc["body"],
                            page=sp["page"], radius=t["radius"])
        try:
            meta = filestore.write_file(inp.file_name, page)
        except filestore.FileStoreError as exc:
            return {"error": str(exc)}
        return {"rendered": True, "theme": inp.theme.strip().lower(),
                "download": f"/files/{meta['name']}", "bytes": meta["bytes"]}
    return {"error": f"unknown action '{inp.action}'", "actions": ["list", "get", "render"]}
