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
    "spec_first": {
        "when": "start a non-trivial build or feature (pin down what before how)",
        "brief": (
            "Do not jump into code. First tease out what the user actually wants: ask the few "
            "questions that change the design, one or two at a time, until you can state the goal, "
            "the constraints, and what 'done' looks like. Play it back in chunks short enough to "
            "read - problem, approach, what is explicitly out of scope - and get a yes on each "
            "before moving on. Only then propose a plan: ordered steps small enough that a careless "
            "junior could follow them, each with how you will know it worked. Build nothing until "
            "the plan gets a go."
        ),
    },
    "tdd_flow": {
        "when": "write or change code with tests driving (red/green discipline)",
        "brief": (
            "Work red/green. For each behavior: write the failing test first and watch it fail for "
            "the right reason - a test that never fails proves nothing. Then write the smallest "
            "change that turns it green, nothing more. Then clean up with the tests green: rename, "
            "dedupe, simplify. One behavior per cycle; keep the suite green between cycles. Do not "
            "bank features ahead of tests (YAGNI), and do not copy-paste a third time (DRY). If a "
            "test is hard to write, that is the design talking - simplify the interface first."
        ),
    },
    "verify_done": {
        "when": "before declaring any work finished",
        "brief": (
            "Never say done on faith. Before reporting completion: run the actual test suite and "
            "quote the real numbers, not the expected ones. Open the artifact that matters - the "
            "page, the file, the output - and look at it. Re-read the request and check every "
            "asked-for thing is present. Anything you could not check gets named as unverified, "
            "with what would check it. 'Should work' is not verified. If verification surfaces a "
            "problem, fix it and verify again before reporting."
        ),
    },
    "storyscope": {
        "when": "write or revise fiction that reads human, not AI-default",
        "brief": (
            "Write fiction against the documented AI defaults (StoryScope, COLM 2026). Before drafting, "
            "roll story dice and state them in one line: structure (strictly linear, or one non-linear "
            "move like a flashback, time jump, or opened-at-the-end), point of view, ending (resolved, "
            "open, or ambiguous), subplot count (0-2). Then the rules. Never state the theme or a lesson "
            "learned - trust the reader to infer it. Give the protagonist's key choice a real moral cost. "
            "Leave at least one loose end untied. Mix how emotion lands: sometimes name it plainly "
            "(she was afraid), do not always route it through bodies, weather, and lamplight. Name real "
            "works, places, and things when it fits instead of vague allusions. Vary escalation - no flat "
            "arc, and don't close every story with a quiet epilogue. Allow one scene that exists for "
            "texture, not plot. Read the draft back and cut any sentence that explains what the story means."
        ),
    },
    "reason_route": {
        "when": "match reasoning effort to problem complexity (Illusion-of-Thinking counters)",
        "brief": (
            "Size the ask before spending tokens on it. Simple lookup or short answer: answer directly, "
            "no deliberation dump - overthinking easy problems wastes budget and can talk you out of a "
            "correct first answer. Layered judgment: think, then answer. Anything needing many EXACT "
            "steps - puzzle move sequences, long arithmetic, itinerary or state tracking, multi-step "
            "derivations: never simulate the steps in prose; models collapse on long exact traces. "
            "Write a small self-verifying solver and call exact_solve, then report only the verified "
            "answer. If a problem might be impossible, run a quick feasibility check in code before "
            "committing to a long attempt; if it is provably unsolvable, say so with the evidence "
            "instead of proposing moves. Never cut effort because a problem looks hard; never burn a "
            "long chain on something that needed two sentences."
        ),
    },
    "seo_web": {
        "when": "build a website or landing page that can actually rank (claude-seo knowledge, MIT)",
        "brief": (
            "Build rankable, not just pretty. Semantic HTML5: one h1, logical h2/h3 outline, lang, "
            "charset, viewport. Title 30-60 chars with the primary term; meta description 70-160 that "
            "earns the click. Canonical link, og:title/description/image, twitter:card. JSON-LD in the "
            "initial HTML (never JS-injected) with active types only - Organization, WebSite, WebPage, "
            "Article, Product, Service, LocalBusiness as fits; never HowTo or SpecialAnnouncement; "
            "FAQPage has no rich-result benefit since May 2026 (use QAPage for real Q&A); absolute URLs "
            "inside schema. Every informative image gets descriptive alt text; all resources over https; "
            "keep critical content inside the first 2MB of HTML. E-E-A-T: visible author/about, contact "
            "details, original content over filler. Internal links with descriptive anchors. Before "
            "delivering, run seo_audit on the final HTML and fix every fail and warn, then re-run."
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
