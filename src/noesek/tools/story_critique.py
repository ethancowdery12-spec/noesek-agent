"""StoryScope-informed fiction critique (roadmap item 60).

Grounded in Russell et al., "StoryScope: Investigating idiosyncrasies in AI
fiction" (COLM 2026, arXiv:2604.03136): AI stories separate from human ones at
the DISCOURSE level - over-explained themes, tidy single-track plots, low
temporal complexity, morally unambiguous protagonists, emotion always routed
through bodies/senses, vague instead of named references, flat escalation.
Supplementary: Verbalized Sampling (arXiv:2510.01171) and the narrative-
flattening line of work (arXiv:2605.27878) - diversity collapses at the
narrative-choice level, so critique must target choices, not prose surface.

Own implementation: one model pass over the draft against an explicit rubric
of the paper's documented AI-typical patterns (findings, own words), lenient
JSON parsing, graceful degradation when the model returns unparseable text.
No new dependencies.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field


class StoryCritiqueInput(BaseModel):
    story: str = Field(min_length=50, max_length=20000,
                       description="The fiction draft (or excerpt) to critique")
    focus: str = Field(default="", max_length=500,
                       description="Optional: what to weight most, e.g. 'the ending' or 'dialogue'")


# Each check is one documented AI-vs-human narrative tendency, phrased as a
# question about narrative CHOICES (not style). verdict: ai | human | mixed.
CHECKS = [
    ("stated_theme", "Does the narrator spell out the story's theme or a lesson learned instead of trusting the reader?"),
    ("tidy_ending", "Is the ending fully resolved (acceptance/understanding/epilogue) rather than open or ambiguous?"),
    ("linear_time", "Does the story run strictly chronologically with no flashbacks, time jumps, or reordered revelations?"),
    ("single_track", "Is there exactly one plot thread with no subplots and no loose ends?"),
    ("clean_hero", "Are the protagonist's key choices morally comfortable rather than costly or ambiguous?"),
    ("bodily_emotion", "Is emotion always rendered through physical sensation/setting, never named plainly?"),
    ("vague_references", "Are cultural references vague allusions rather than specific named works, places, or things?"),
    ("flat_escalation", "Does event intensity stay flat instead of rising, dipping, and turning?"),
    ("debate_dialogue", "Does dialogue serve philosophical debate more than lived, transactional conversation?"),
    ("sealed_narration", "Does the narration behave as if no reader exists (no asides, no address, no fourth-wall play)?"),
]

_VERDICTS = ("ai", "human", "mixed")


def _parse(raw: str) -> list[dict] | None:
    """Lenient JSON parse: find the first [...] block and validate shape."""
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    out = []
    for item in data:
        if not isinstance(item, dict) or item.get("verdict") not in _VERDICTS:
            continue
        out.append({"check": str(item.get("check", ""))[:60],
                    "verdict": item["verdict"],
                    "evidence": str(item.get("evidence", ""))[:300],
                    "suggestion": str(item.get("suggestion", ""))[:300]})
    return out or None


def story_critique_handler(llm_resolver):
    async def f(inp: StoryCritiqueInput) -> dict:
        llm = await llm_resolver()
        rubric = "\n".join(f'{i+1}. "{name}": {q}' for i, (name, q) in enumerate(CHECKS))
        focus = f"\nWeight this most: {inp.focus}" if inp.focus.strip() else ""
        prompt = (
            "You are a fiction editor. Critique the draft below against these ten narrative-choice checks. "
            "For each, judge whether the draft shows the AI-typical or the human-typical pattern, quoting "
            "at most one short phrase as evidence, and give one concrete suggestion.\n\n"
            f"{rubric}\n\n"
            'Return ONLY a JSON array: [{"check": "<name>", "verdict": "ai"|"human"|"mixed", '
            '"evidence": "<short quote or observation>", "suggestion": "<one concrete fix>"}]'
            f"{focus}\n\nDRAFT:\n{inp.story}"
        )
        reply = await llm.complete([{"role": "user", "content": prompt}], [])
        raw = reply.content or ""
        rows = _parse(raw)
        if rows is None:
            return {"error": "critique parse failed", "raw_head": raw[:400]}
        counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in _VERDICTS}
        return {"checks": rows, "ai_typical": counts["ai"], "human_typical": counts["human"],
                "mixed": counts["mixed"],
                "note": "ai-typical checks are the documented AI-fiction defaults (StoryScope); "
                        "fix those first, then re-run."}
    return f
