"""Own-code recap turn for long, underspecified conversations.

Basis: Laban et al., "LLMs Get Lost In Multi-Turn Conversation" (Microsoft
Research / Salesforce Research, arXiv 2505.06120). In that paper, instructions
revealed piece by piece over several turns scored far below the same
instruction given at once, and restating every piece in one final turn
("Recap") recovered part, not all, of the gap. This tool builds that recap
turn from the user's messages: every requirement the user stated, de-duplicated
and in order, so a fresh turn or fresh chat can start from one complete
instruction. It also flags the paper's named failure patterns it can see in the
transcript (assistant answered before the user finished specifying, very long
assistant replies, conflicting numbers). Heuristic text analysis only; no model
call, no claim about any specific model's score.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=20000)


class ConvoRecapInput(BaseModel):
    turns: list[Turn] = Field(min_length=1, max_length=200)
    max_requirements: int = Field(default=40, ge=1, le=100)
    long_reply_words: int = Field(default=350, ge=50, le=5000)


_REQ = re.compile(r"\b(must|should|need|needs|want|wants|only|never|always|don't|do not|avoid|make sure|has to|have to|"
                  r"at least|at most|no more than|exactly|by \w+day|deadline|use|using|without|include|exclude|format|"
                  r"limit|max|min)\b|\d", re.I)
_Q = re.compile(r"\?\s*$")


def _sentences(text):
    flat = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]


def _key(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def convo_recap(inp: ConvoRecapInput) -> dict:
    reqs, seen = [], {}
    for i, t in enumerate(inp.turns):
        if t.role != "user":
            continue
        for s in _sentences(t.text):
            if _Q.search(s) and not re.search(r"\d", s):
                continue
            if _REQ.search(s) or i == 0:
                k = _key(s)
                if k and k not in seen:
                    seen[k] = len(reqs)
                    reqs.append({"turn": i, "text": s[:300]})
    user_turns = [i for i, t in enumerate(inp.turns) if t.role == "user"]
    flags = []
    for i, t in enumerate(inp.turns):
        if t.role == "assistant":
            w = len(t.text.split())
            later = [u for u in user_turns if u > i]
            if w > inp.long_reply_words:
                flags.append({"turn": i, "pattern": "long_reply", "detail": f"{w} words; long replies add assumptions the user did not state"})
            if later and re.search(r"```|^\s*(?:def |class |SELECT |#include)|final (?:answer|version)|here(?:'s| is) (?:the|your) (?:complete|full|final)", t.text, re.I | re.M):
                flags.append({"turn": i, "pattern": "answered_early",
                              "detail": f"gave a full solution, then the user added {len(later)} more message(s)"})
    nums = {}
    for r in reqs:
        for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(words?|items?|pages?|days?|hours?|minutes?|%|px|dollars?|usd|users?|rows?|lines?|bullets?|sentences?|characters?|chars?)\b", r["text"], re.I):
            nums.setdefault(m.group(2).lower().rstrip("s"), []).append((m.group(1), r["turn"]))
    for unit, vals in nums.items():
        if len({v for v, _ in vals}) > 1:
            flags.append({"pattern": "conflicting_numbers", "detail": f"different values for '{unit}': " + ", ".join(f"{v} (turn {t})" for v, t in vals)})
    shown = reqs[: inp.max_requirements]
    recap = ("Here is everything I have asked for so far, as one instruction. If an item conflicts with a later one, the later one wins.\n"
             + "\n".join(f"{n}. {r['text']}" for n, r in enumerate(shown, 1)))
    return {"user_turns": len(user_turns), "requirements": shown, "truncated": len(reqs) > len(shown),
            "recap_turn": recap if shown else "", "flags": flags,
            "advice": "Send the recap turn (or start a new chat with it) once a conversation passes a handful of turns or after an answer you disagree with.",
            "executed": False,
            "caveat": "Sentence-level heuristics: it may keep a sentence that is not a requirement or miss an unmarked one. Read the recap before relying on it."}
