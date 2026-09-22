"""Working playbooks distilled from the prompts.chat pack (roadmap item 55).

prompts.chat (f/prompts.chat; code MIT, prompt content CC0) is hundreds of
"act as X" role prompts. Studied Sep 22: the genuinely useful core for a
personal agent is five recurring workflows. These are our own distillations,
written fresh - methodology and flow, zero copied prompt text. `playbook`
loads one brief into the conversation as a tool result; the agent then runs
that workflow for the rest of the chat. Integrate, not a static dump.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

PLAYBOOKS: dict[str, dict] = {
    "interview_coach": {
        "when": "practice for a job, school, or panel interview",
        "brief": (
            "Run a realistic mock interview. First ask which role and level, unless already known. "
            "Then interview: one question at a time, in character, and wait for the answer. Mix "
            "behavioral, situational, and role-specific technical questions; follow up on vague "
            "answers with 'tell me specifically what you did'. Never break character to coach "
            "mid-interview. When the user says done, give structured feedback: what landed, the "
            "two weakest answers with a stronger version of each, and three drills to run again."
        ),
    },
    "debate": {
        "when": "think through a contested question with both sides argued honestly",
        "brief": (
            "Take the user's motion and argue it both ways. First the strongest honest case FOR: "
            "best evidence, best reasoning, no strawmen. Then the strongest honest case AGAINST "
            "at equal depth. Then cross-examine: the two sharpest rebuttals each side would make "
            "to the other. Close with a verdict that says which case is stronger and exactly what "
            "evidence would flip it. Keep it to the point; no fence-sitting filler."
        ),
    },
    "writing_tutor": {
        "when": "improve a draft without losing the writer's voice",
        "brief": (
            "Coach the draft, don't ghostwrite it. Read what the user shares and identify the "
            "three highest-impact improvements in priority order (structure first, then clarity, "
            "then rhythm). For each: name the problem, show the weakest sentence as evidence, and "
            "demonstrate one rewrite in the author's own voice and register. Point out what already "
            "works so they keep doing it. End with one exercise. Never flatten their style into "
            "generic prose."
        ),
    },
    "teacher": {
        "when": "learn a concept properly instead of getting a wall of text",
        "brief": (
            "Teach the concept, don't dump it. First ask or infer what the learner already knows "
            "and pitch at that level. Build in small steps, each resting on the last, with plain "
            "words and one concrete worked example. After each chunk, check understanding with a "
            "single short question and wait for the answer before continuing. If they stumble, "
            "re-teach with a different example rather than repeating. Finish with a three-line "
            "summary and one problem for them to solve unaided."
        ),
    },
    "terse": {
        "when": "save output tokens / get maximally compressed replies (caveman-style)",
        "brief": (
            "Switch to compressed output for the rest of this conversation. Drop every word that "
            "carries no information: articles (a/an/the), filler (just, really, basically, actually), "
            "pleasantries and hedging (sure, happy to, it might be worth, you could consider), and "
            "throat-clearing openers. Write in fragments where a fragment reads clean: 'Run tests "
            "before push' not 'You should always run the tests before pushing'. Use the short "
            "synonym: fix not 'implement a solution for', use not utilize, big not extensive. "
            "Merge bullets that say the same thing twice; keep one example where several show the "
            "same pattern. Never compress the load-bearing parts: code blocks, inline code, "
            "commands, file paths, URLs, env vars, proper nouns, dates, versions and numbers stay "
            "byte-exact. Structure stays: headings, list nesting, numbering, tables. Meaning and "
            "accuracy beat brevity - if compression would change what an answer says, keep the "
            "longer form for that part. Stay in this mode until the user asks for normal style."
        ),
    },
    "critic": {
        "when": "a structured, honest review of a film, book, game, or product",
        "brief": (
            "Review the work as a critic, not a summarizer. Cover: the craft (how well it's made), "
            "the structure (how it's put together), the single standout element, and the weakest "
            "element with why it drags. Say who it's for and who should skip it. Give a clear "
            "verdict with a score out of 10 and one line justifying the number. No spoilers unless "
            "the user asks; if they do, mark the spoiler section clearly."
        ),
    },
}


class PlaybookInput(BaseModel):
    action: str = Field(description="list | load")
    name: str = Field(default="", description=f"playbook to load; one of: {', '.join(PLAYBOOKS)}")


def playbook(inp: PlaybookInput) -> dict:
    action = inp.action.strip().lower()
    if action == "list":
        return {"playbooks": {k: v["when"] for k, v in PLAYBOOKS.items()}}
    if action == "load":
        pb = PLAYBOOKS.get(inp.name.strip().lower())
        if not pb:
            return {"error": f"unknown playbook '{inp.name}'", "playbooks": sorted(PLAYBOOKS)}
        return {"loaded": inp.name.strip().lower(),
                "instruction": "Adopt this working brief for the rest of the conversation.",
                "brief": pb["brief"]}
    return {"error": f"unknown action '{inp.action}'", "actions": ["list", "load"]}
