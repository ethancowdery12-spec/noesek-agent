"""Humanizer: rewrite AI-sounding text so it reads like a person wrote it.

Idea study of `blader/humanizer` (MIT) and Wikipedia's "Signs of AI
writing" (WikiProject AI Cleanup, CC BY-SA). This is our own deterministic
implementation: a fixed rule set does safe mechanical rewrites (filler
openers/closers, em dashes, curly quotes, dead-weight phrases) and flags
inflated vocabulary with suggestions instead of silently guessing tone.
No model call, no dependencies.
"""
from __future__ import annotations

import re

from pydantic import BaseModel


class HumanizeInput(BaseModel):
    text: str


# Safe one-word swaps: the replacement never changes the meaning.
SAFE_SWAPS = {
    "utilize": "use", "utilizes": "uses", "utilized": "used",
    "utilizing": "using", "leverage": "use", "leverages": "uses",
    "leveraged": "used", "leveraging": "using", "commence": "start",
    "endeavor": "try", "endeavors": "tries", "ascertain": "find out",
    "facilitate": "help", "facilitates": "helps",
    "delve into": "dig into", "delve": "dig",
    "plethora": "plenty", "myriad": "many",
}

# Inflated vocabulary: flag with a suggestion, never auto-swap (tone risk).
FLAG_WORDS = {
    "crucial": "essential or just say why it matters",
    "pivotal": "key",
    "vibrant": "lively or drop it",
    "streamline": "simplify",
    "holistic": "complete or drop it",
    "nuanced": "subtle or explain the nuance",
    "comprehensive": "full or drop it",
    "robust": "solid",
    "seamless": "smooth",
    "foster": "build",
    "empower": "let",
    "navigate": "deal with or get through",
    "craft": "make",
    "elevate": "improve",
    "underscore": "stress",
    "garner": "get",
    "intricate": "detailed",
    "showcase": "show",
    "groundbreaking": "new",
    "renowned": "well-known",
    "profound": "deep",
    "boasts": "has",
    "landscape": "field or scene",
    "tapestry": "mix",
    "testament": "sign",
    "realm": "area",
    "beacon": "standout",
    "embark": "start",
    "unleash": "start or drop it",
    "unlock": "open up",
    "revolutionize": "change",
}

# Filler phrases: safe to delete outright.
FILLER_PHRASES = [
    r"I'd be happy to (?:help|assist)[^.!?]*[.!?]",
    r"I hope this (?:helps|email finds you well)[^.!?]*[.!?]",
    r"[Pp]lease don't hesitate to[^.!?]*[.!?]",
    r"[Ll]et me know if you need anything else[.!?]",
    r"[Ll]et me know if you have any (?:questions|concerns)[.!?]",
    r"[Ff]eel free to reach out[^.!?]*[.!?]",
    r"[Ii]t's important to note that\s*",
    r"[Ii]t goes without saying that\s*",
    r"[Ii]n today's (?:fast-paced|ever-evolving)[^,.]*,\s*",
    r"[Ii]n conclusion,\s*",
    r"[Tt]o (?:summarize|sum up),\s*",
    r"[Aa]s an AI (?:language model|assistant)[^.!?]*[.!?]",
]

# Stylistic constructions to flag (regex, suggestion).
FLAG_PATTERNS = [
    (r"\bnot just\b[^.!?]{3,80}?\bbut (?:also\b)?", "'not just X, but Y' is an AI tell - split into two claims"),
    (r"\bIt's not [^,.!?]{2,60},\s*it's\b", "'It's not X, it's Y' construction - state the point directly"),
    (r"\bWhether you're\b[^.!?]{3,120}", "'Whether you're A or B' framing - pick the real audience"),
    (r"\bserves as\b", "'serves as' - use 'is'"),
    (r"\bstands as\b", "'stands as' - use 'is'"),
]


def _swap_word(match: re.Match) -> str:
    word = match.group(0)
    replacement = SAFE_SWAPS[word.lower()]
    return replacement.capitalize() if word[0].isupper() else replacement


def humanize_text(raw: str) -> dict:
    """Rewrite AI-sounding text; returns the rewrite plus what changed."""
    applied: list[str] = []
    flags: list[dict] = []
    out = raw

    # Mechanical: punctuation normalization.
    if "\u2014" in out or "\u2013" in out:
        out = re.sub(r"\s*[\u2013\u2014]\s*", " - ", out)
        applied.append("em/en dashes -> plain dashes")
    for curly, straight in (("\u201c", '"'), ("\u201d", '"'),
                            ("\u2018", "'"), ("\u2019", "'")):
        if curly in out:
            out = out.replace(curly, straight)
            if "curly quotes -> straight quotes" not in applied:
                applied.append("curly quotes -> straight quotes")

    # Filler openers/closers.
    for pattern in FILLER_PHRASES:
        new = re.sub(pattern, "", out)
        if new != out:
            out = new
            applied.append(f"removed filler: /{pattern[:40]}/")

    # Safe vocabulary swaps (word-boundary, case-preserving).
    if SAFE_SWAPS:
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(w) for w in SAFE_SWAPS) + r")\b",
            re.IGNORECASE)
        new = pattern.sub(_swap_word, out)
        if new != out:
            out = new
            applied.append("swapped dead-weight verbs (utilize/leverage/delve -> use/dig)")

    # Flags: inflated vocabulary and AI-tell constructions.
    for word, suggestion in FLAG_WORDS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", out, re.IGNORECASE):
            flags.append({"pattern": word, "suggestion": suggestion})
    for pattern, suggestion in FLAG_PATTERNS:
        if re.search(pattern, out, re.IGNORECASE):
            flags.append({"pattern": pattern[:40], "suggestion": suggestion})

    # Clean up whitespace left by removals.
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()

    return {
        "humanized_text": out,
        "unchanged": out == raw.strip(),
        "applied_rewrites": applied,
        "flags": flags,
        "note": ("flags are advisory - rewrite those phrases by hand to "
                 "fit the voice you want; facts and names are untouched"),
    }


async def humanize(inp: HumanizeInput) -> dict:
    return humanize_text(inp.text)
