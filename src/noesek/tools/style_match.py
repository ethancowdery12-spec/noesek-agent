"""Own-code reference match: does the built page actually follow the style reference?

The taste video's point is that the hard part is knowing exactly what you want.
This turns a reference (a palette, fonts and radii, or a reference HTML/CSS
snippet) into numbers and compares them with what the built page uses: palette
coverage by perceptual colour distance (CIE76 in Lab), off-palette colours,
font families and corner radii. It judges nothing subjective and renders
nothing; it reports what matches and what drifted.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


class StyleMatchInput(BaseModel):
    built_html: str = Field(min_length=1, max_length=400_000, description="the page that was built")
    reference_html: str = Field(default="", max_length=400_000, description="reference page or CSS to match")
    palette: list[str] = Field(default_factory=list, max_length=40, description="reference hex colours, e.g. #0a0a0a")
    fonts: list[str] = Field(default_factory=list, max_length=10, description="reference primary font families")
    radii_px: list[int] = Field(default_factory=list, max_length=10, description="reference corner radii in px")
    tolerance: float = Field(default=12.0, gt=0, le=100, description="max Lab distance counted as a match")


def _norm(h: str) -> str:
    h = h.lstrip("#").lower()
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)


def _lab(h: str):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    x = (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.95047
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    z = (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    la, lb = _lab(_norm(a)), _lab(_norm(b))
    return round(sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5, 1)


def _css(src: str) -> str:
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", src, re.S | re.I)
    inline = re.findall(r"style\s*=\s*\"([^\"]*)\"", src, re.I)
    return "\n".join(blocks + inline) if (blocks or inline) else src


def _colors(css: str) -> list[str]:
    seen = []
    for m in _HEX.finditer(css):
        c = _norm(m.group(0))
        if c not in seen:
            seen.append(c)
    return seen


def _fonts(css: str) -> list[str]:
    out = []
    for m in re.findall(r"font-family\s*:\s*([^;}\"]+)", css, re.I):
        f = m.split(",")[0].strip().strip("'\"").lower()
        if f and f not in out:
            out.append(f)
    return out


def _radii(css: str) -> list[int]:
    return sorted({int(x) for x in re.findall(r"border-radius\s*:\s*(\d+)px", css, re.I)})


def style_match(inp: StyleMatchInput) -> dict:
    built = _css(inp.built_html)
    ref_css = _css(inp.reference_html) if inp.reference_html.strip() else ""
    try:
        ref_colors = [_norm(c) for c in inp.palette if _HEX.fullmatch(c.strip())] or _colors(ref_css)
    except Exception:
        ref_colors = []
    bad = [c for c in inp.palette if not _HEX.fullmatch(c.strip())]
    ref_fonts = [f.lower() for f in inp.fonts] or _fonts(ref_css)
    ref_radii = inp.radii_px or _radii(ref_css)
    if not (ref_colors or ref_fonts or ref_radii):
        return {"ok": False, "error": "no reference given: pass palette, fonts, radii_px or reference_html", "bad_palette_entries": bad}
    used = _colors(built)
    pal = []
    for rc in ref_colors:
        best = min(((delta_e(rc, u), u) for u in used), default=(None, None))
        pal.append({"reference": rc, "nearest_built": best[1], "delta_e": best[0],
                    "matched": best[0] is not None and best[0] <= inp.tolerance})
    off = []
    for u in used:
        if ref_colors and min(delta_e(u, rc) for rc in ref_colors) > inp.tolerance:
            off.append(u)
    bf = _fonts(built)
    fonts = {"reference": ref_fonts, "built": bf, "missing": [f for f in ref_fonts if f not in bf],
             "extra": [f for f in bf if ref_fonts and f not in ref_fonts]} if ref_fonts else None
    br = _radii(built)
    radii = {"reference": sorted(ref_radii), "built": br, "missing": [r for r in sorted(ref_radii) if r not in br],
             "extra": [r for r in br if ref_radii and r not in ref_radii]} if ref_radii else None
    cov = round(sum(p["matched"] for p in pal) / len(pal), 2) if pal else None
    clean = (cov in (None, 1.0)) and not off and not (fonts and fonts["missing"]) and not (radii and radii["missing"])
    return {"ok": True, "matches_reference": bool(clean), "palette_coverage": cov, "palette": pal,
            "off_palette_colors": off, "fonts": fonts, "radii": radii, "tolerance_delta_e": inp.tolerance,
            "bad_palette_entries": bad,
            "caveat": "Compares literal hex colours, font-family names and px radii found in the markup. Named colours, CSS variables and rendered output are not resolved. Does not judge layout or taste."}
