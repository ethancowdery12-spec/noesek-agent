"""Natural-reading rewriter (roadmap item 48, expanded scope Sep 21).

Ethan's call, his content: take AI-sounding text he owns and make it read
like a person wrote it - kill inflated vocabulary, formulaic openers,
hedging stacks, and uniform rhythm. This extends the humanizer's
mechanical passes with structure-level rules. It makes no claim about any
detector; the goal is text that reads naturally, nothing else.

Own deterministic implementation (idea study: Wikipedia "Signs of AI
writing" and the StoryScope detector lesson - detectors key on structural
template, so rhythm and opener variety matter as much as word choice).
No model call, no dependencies.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .humanize import humanize_text


class RewriteNaturalInput(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


# Hedging stacks and throat-clearing: the claim almost always stands alone.
HEDGE_CUTS = [
    r"[Ii]t is important to note that\s*",
    r"[Ii]t should be noted that\s*",
    r"[Ii]t is worth noting that\s*",
    r"[Ii]t's worth mentioning that\s*",
    r"[Ii]t may be worth considering that\s*",
    r"[Ii]t could be argued that\s*",
    r"[Ii]t is (?:often|generally|commonly) said that\s*",
    r"[Oo]ne might (?:say|argue|consider) that\s*",
]
HEDGE_COLLAPSES = [
    (r"\bmay potentially\b", "may"),
    (r"\bcould possibly\b", "could"),
    (r"\bmight be able to\b", "could"),
    (r"\bmay be able to\b", "can"),
    (r"\bIn order to\b", "To"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bat this point in time\b", "now"),
    (r"\bin the event that\b", "if"),
    (r"\ba wide (?:range|array|variety) of\b", "many"),
    (r"\bplays? a (?:key|crucial|critical|vital|significant) role in\b", "is central to"),
    (r"\bserves as a testament to\b", "shows"),
]
# Formulaic sentence openers: safe to delete at the start of a sentence.
OPENER_CUTS = [
    r"(?<=[.!?]\s)(?:Furthermore|Moreover|Additionally|In addition|What'?s more|Notably|Importantly|Interestingly|Significantly),\s+",
    r"^(?:Furthermore|Moreover|Additionally|In addition|What'?s more|Notably|Importantly|Interestingly|Significantly),\s+",
    r"(?<=[.!?]\s)(?:First(?:ly)?|Second(?:ly)?|Third(?:ly)?|Finally),\s+",
]
TRIAD_RE = re.compile(r"\b\w+(?: \w+)?, \w+(?: \w+)?, and \w+")
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+")


def _sentence_stats(text: str) -> dict:
    sentences = [s.strip() for s in SENTENCE_RE.findall(text) if s.strip()]
    if len(sentences) < 3:
        return {"sentences": len(sentences)}
    lengths = [len(s.split()) for s in sentences]
    avg = sum(lengths) / len(lengths)
    if avg == 0:
        return {"sentences": len(sentences)}
    variance = sum((n - avg) ** 2 for n in lengths) / len(lengths)
    cv = (variance ** 0.5) / avg
    note = None
    if cv < 0.25:
        note = ("uniform rhythm: every sentence lands at roughly the same length, "
                "which reads machine-written - split one long point into two short "
                "sentences or merge two short ones")
    return {"sentences": len(sentences), "avg_words": round(avg, 1), "rhythm": note}


def rewrite_natural_text(raw: str) -> dict:
    applied: list[str] = []
    out = raw

    for pattern in HEDGE_CUTS:
        new = re.sub(pattern, "", out)
        if new != out:
            out = new
            applied.append("cut throat-clearing opener (it is important to note...)")
    for pattern, replacement in HEDGE_COLLAPSES:
        new = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
        if new != out:
            out = new
            applied.append(f"collapsed hedge stack: /{pattern[:40]}/ -> {replacement}")
    for pattern in OPENER_CUTS:
        new = re.sub(pattern, lambda m: "", out)
        if new != out:
            out = new
            applied.append("removed formulaic transition opener (Furthermore/Moreover/Firstly...)")

    # Delve family (humanize covers only the bare stem).
    new = re.sub(r"\bdelve([sd]?)\b|\bdelving\b",
                 lambda m: {"s": "digs", "d": "dug", "": "dig"}[m.group(1) or ""] if m.group(0).endswith(("e", "es", "ed")) else "digging",
                 out, flags=re.IGNORECASE)
    if new != out:
        out = new
        applied.append("swapped delve family (delved/delves/delving -> dug/digs/digging)")

    # Then the humanizer's mechanical passes (dashes, quotes, filler, vocab).
    hz = humanize_text(out)
    out = hz["humanized_text"]
    applied.extend(hz["applied_rewrites"])
    flags = list(hz["flags"])

    # Triadic rhythm: flag only (rewriting a list risks changing meaning).
    if len(TRIAD_RE.findall(out)) >= 2:
        flags.append({"pattern": "repeated three-item lists",
                      "suggestion": "the 'X, Y, and Z' cadence twice or more reads templated - keep the one that earns it"})

    # Restore sentence-start capitals after opener cuts.
    out = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)

    # Collapse double spaces left by cuts; fix space-before-punctuation.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([,.;:!?])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()

    return {"text": out, "applied": applied, "flags": flags, "structure": _sentence_stats(out)}


async def rewrite_natural(inp: RewriteNaturalInput) -> dict:
    return rewrite_natural_text(inp.text)
