"""Parallel-variant generation (roadmap item 53).

Idea from abi/screenshot-to-code (MIT, studied): run N candidate
generations in parallel with different style lenses, then pick the best
with a judge pass and show the rest. Applied to creative/generative chat
tasks: names, subject lines, taglines, bios, drafts - anywhere one shot
is a lottery ticket.

Own implementation: N concurrent model calls through the chat's resolved
adapter (per-chat model override respected), one judge call, graceful
fallback when the judge fails. No new dependencies.
"""
from __future__ import annotations

import asyncio
import re

from pydantic import BaseModel, Field


class GenerateVariantsInput(BaseModel):
    task: str = Field(min_length=3, max_length=2000,
                      description="What to create, e.g. 'three tagline options for a dog-sitting app called Biscuit'")
    n: int = Field(default=3, ge=2, le=5, description="How many distinct candidates to generate (2-5)")
    context: str | None = Field(default=None, max_length=1000,
                                description="Optional audience/tone/constraints the candidates must fit")


# Style lenses force diversity the way parallel workers differ on their own;
# without them, N samples of the same prompt cluster together.
LENSES = [
    "direct and punchy",
    "warm and conversational",
    "precise and formal",
    "bold and unexpected",
    "minimal - as few words as possible",
]


def generate_variants_handler(llm_resolver):
    """llm_resolver: async callable returning the adapter for this chat."""

    async def h(inp: GenerateVariantsInput):
        async def _one(lens: str) -> str | None:
            llm = await llm_resolver()
            prompt = (f"{inp.task}\n\nWrite ONE candidate answer, in a {lens} style. "
                      "Output only the candidate itself - no preamble, no numbering, no quotes.")
            if inp.context:
                prompt += f"\nIt must fit this context: {inp.context}"
            try:
                reply = await llm.complete(
                    [{"role": "user", "content": prompt}], [])
                text = (reply.content or "").strip()
                return text or None
            except Exception:
                return None

        lenses = (LENSES * ((inp.n // len(LENSES)) + 1))[: inp.n]
        results = await asyncio.gather(*(_one(lens) for lens in lenses))
        variants = [{"n": i + 1, "lens": lens, "text": text}
                    for i, (lens, text) in enumerate(zip(lenses, results)) if text]
        if not variants:
            return {"error": "all candidate generations failed - try again"}
        pick, reason = variants[0]["n"], "judge unavailable - showing the first candidate"
        if len(variants) > 1:
            numbered = "\n\n".join(f"[{v['n']}] ({v['lens']})\n{v['text']}" for v in variants)
            judge_prompt = (f"Task: {inp.task}\n"
                            + (f"Context: {inp.context}\n" if inp.context else "")
                            + f"\nCandidates:\n{numbered}\n\n"
                            "Pick the single best candidate for the task. Reply with ONLY: "
                            "PICK <number> - <one short reason>")
            try:
                llm = await llm_resolver()
                jreply = await llm.complete([{"role": "user", "content": judge_prompt}], [])
                m = re.match(r"\s*PICK\s+(\d+)\s*-\s*(.+)", (jreply.content or "").strip(), re.IGNORECASE | re.DOTALL)
                if m and any(v["n"] == int(m.group(1)) for v in variants):
                    pick, reason = int(m.group(1)), m.group(2).strip()[:300]
            except Exception:
                pass
        return {"variants": variants, "pick": pick, "reason": reason,
                "note": "the pick is the recommended one; the rest are alternates"}

    return h
