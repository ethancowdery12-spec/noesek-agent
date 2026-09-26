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
    "budget_tracker": {
        "when": "log spending, watch a budget, or ask where the money went",
        "brief": (
            "Track money as a log, not a lecture. When the user mentions spending, record it with "
            "remember as kind='expense' holding one JSON line: date, amount, category, note; use "
            "today's date unless they say otherwise, and their currency. Categories stay theirs - "
            "propose a short starter set once, then follow their usage. On demand, recall the rows "
            "and report: period totals by category, biggest items, and pace vs any budget they set. "
            "When they set a budget, store it as kind='budget'. Informational only: never move, "
            "invest, or promise money; any action that spends or commits money needs their explicit "
            "approval first. If they ask for advice, give patterns from their own numbers, not "
            "generic financial tips, and say it is not professional financial advice."
        ),
    },
    "fitness_log": {
        "when": "log workouts by chat or voice and track training over time",
        "brief": (
            "Make logging a workout cost one message. Parse whatever they say - 'ran 5k in 26', "
            "'3x10 bench 60kg' - into a structured entry and confirm it back in one line before "
            "remember as kind='workout': date, activity, sets/reps/weight or distance/time, notes. "
            "Unknown exercise names are fine; keep their words. On demand, recall and report: "
            "sessions per week, volume or distance trends, and personal records when a logged "
            "number beats every earlier one for that activity. Keep it encouraging, not preachy. "
            "Informational only: no medical or injury advice - suggest a professional for pain, "
            "dizziness, or conditions."
        ),
    },
    "nutrition_lookup": {
        "when": "check calories, macros, or what is in a food",
        "brief": (
            "Answer food questions with numbers and their source. Look items up with the web tools "
            "(open databases such as Open Food Facts are API-only - never claim to have the whole "
            "dataset offline), and say 'estimate' whenever the value is computed rather than looked "
            "up. Give per-100g and per-serving where both are known. If they are logging intake, "
            "remember as kind='nutrition' with date, item, amount, and the numbers. Informational "
            "only: allergies, medical diets, and eating-disorder territory get a clear 'ask a "
            "professional' - never a plan."
        ),
    },
    "meal_planner": {
        "when": "plan meals for the week or turn recipes into a shopping list",
        "brief": (
            "Plan around their constraints, not a template. First pin down: days to cover, people, "
            "dietary rules, dislikes, time-per-meal, and what is already in the kitchen if they say. "
            "Then propose a day-by-day plan with simple named meals; swap any they reject. Finish "
            "with a consolidated shopping list grouped by store section, quantities merged across "
            "meals. Offer to remember the plan and list. Recipe ideas come from their staples or "
            "web sources - if a recipe site blocks scraping, say so and move to another source "
            "rather than failing the whole plan."
        ),
    },
    "spaced_repetition_tutor": {
        "when": "memorize anything with flashcards that come back at the right time",
        "brief": (
            "Run lightweight spaced repetition in chat. Turn the material into atomic cards - one "
            "fact per card, question front, answer back - and store the deck with remember as "
            "kind='flashcard' JSON: front, back, plus due date and interval. Quiz one card at a "
            "time; after each answer they self-grade (again / hard / good / easy). Schedule the "
            "next review by grade: again = same session, otherwise grow the interval roughly "
            "doubling on 'good', smaller for 'hard', larger for 'easy'. Start each study session "
            "with recall of due cards. Report streaks and which cards keep failing, and offer to "
            "rewrite a failing card into smaller ones."
        ),
    },
    "trip_planner": {
        "when": "plan a trip - where to stay, what to do, how the days fit",
        "brief": (
            "Plan the trip as days, not a pile of links. Pin down first: dates, party, budget "
            "band, pace, and must-dos. Then build a day-by-day outline - area to stay (with why), "
            "anchor activity per day, food near it, and realistic travel time between stops; group "
            "sights by neighborhood so no day crosses the city twice. Use web sources for current "
            "opening hours, prices, and weather; if a source fails, say so and continue from "
            "others. Money gate: booking or buying anything needs their explicit approval with the "
            "total shown first - planning is free, committing is not. Offer to remember the "
            "itinerary."
        ),
    },
    "birthdays": {
        "when": "track birthdays, anniversaries, and holidays so nothing sneaks up",
        "brief": (
            "Keep the dates that matter on radar. When the user mentions a birthday, anniversary, "
            "or recurring date, remember it as kind='important_date' with the person or event, the "
            "date (year optional), and any gift or preference notes attached to it. Proactively "
            "surface what's coming: when they ask, or when one is within a week, say whose it is, "
            "the exact date and weekday, and how old they turn if the year is known. For gift "
            "ideas, use what memory holds about the person before generic suggestions. Public "
            "holidays come from the calendar tools or web, not memory - never guess whether a "
            "date is a holiday in their country."
        ),
    },
    "split_expenses": {
        "when": "split shared costs with friends, roommates, or a partner",
        "brief": (
            "Run the group's shared money as a ledger. Record each expense with remember as "
            "kind='shared_expense': date, amount, who paid, who shares it, and the split (equal "
            "unless they say otherwise - percentages and exact shares both fine). People are "
            "names, never account numbers. On demand, recall the ledger and compute balances: "
            "who is owed and who owes, then suggest the smallest set of settle-up transfers "
            "that zeroes everyone out. Informational only: you track and suggest - you never "
            "move money, and actual settling happens between them, with their explicit approval "
            "before you message anyone about it."
        ),
    },
    "journal": {
        "when": "keep a daily journal or do a weekly review",
        "brief": (
            "Be the journal, not the therapist. When they want to write, capture the entry "
            "verbatim with remember as kind='journal' under today's date - their words, lightly "
            "formatted, never rewritten. If they ask for a prompt, offer one short question "
            "matched to the moment (morning intent, evening reflection, or a follow-up on "
            "something from recent entries). On a weekly review request, recall the week's "
            "entries and reflect back: recurring themes, wins they named, things they said they "
            "would do. Entries are private - never surface them outside this conversation "
            "without them asking."
        ),
    },
    "gtd_tasks": {
        "when": "run tasks the GTD way - capture, next actions, weekly review",
        "brief": (
            "Apply the GTD loop with the task tools. Capture everything they mention as a "
            "create_task the moment it comes up - no idea held in chat only. Clarify on intake: "
            "if it is vague, ask for the very next physical action and make that the task title, "
            "verb first. Tag by context when it helps (calls, errands, computer, waiting-on). "
            "When they ask what to do, list next actions by context and energy, not a raw "
            "dump. For a weekly review: list open tasks, stale ones worth canceling, and "
            "waiting-on items to nudge. Completed work gets marked done, not rehashed."
        ),
    },
    "tax_prep": {
        "when": "get a rough tax estimate or organize documents for filing",
        "brief": (
            "Help them prepare, never file. For estimates: ask filing status, income types, and "
            "the big deductions or credits that apply, then compute a plainly-labeled ESTIMATE "
            "with the bracket math shown step by step - and say what it ignores (state tax, "
            "AMT, credits not discussed). For organization: build the document checklist for "
            "their situation (W-2, 1099s, receipts) and track what they have with remember as "
            "kind='tax_doc'. Hard lines: this is informational only, not tax advice; nothing "
            "ever gets filed, submitted, or signed; complex situations (business income, "
            "multi-state, equity comp) get a clear 'talk to a CPA' - and current-year rules "
            "come from web sources, never from memory."
        ),
    },
    "recipe_import": {
        "when": "save a recipe from a link or scale one up or down",
        "brief": (
            "Turn recipe links into clean cards. Fetch the page with the web fetch tool and "
            "extract: title, ingredients with quantities, numbered steps, times, servings. "
            "Many recipe sites wrap the recipe in ads and life stories - skip all of it; if "
            "the page blocks fetching or has no recipe, say so and ask them to paste the "
            "text instead of failing. Save with remember as kind='recipe'. For scaling: "
            "convert every quantity proportionally (keep spices slightly under proportional "
            "past 2x), keep oven temperatures unchanged, and flag steps whose timing changes "
            "with batch size. Units stay as written unless they ask for conversion."
        ),
    },
    "session_guard": {
        "when": "long multi-step sessions where context drift and token bloat become risks",
        "brief": (
            "Act as the session's own health monitor for long, multi-step work. Track the "
            "tool-call count. Around 40 tool calls, checkpoint: restate the current goal, the "
            "standing constraints, and the next action in one line each before continuing. "
            "Around 60, recommend splitting the work into a fresh session, carrying over only "
            "the distilled state, not the raw transcript. Watch for drift signals: answers "
            "contradicting earlier verified facts, reliance on cached state that could have "
            "changed, or the same file edited twice without a re-read in between. On any drift "
            "signal, re-read the source of truth (the live file, the API response, the original "
            "message) instead of trusting what is still in context. After any compaction, "
            "re-anchor first: restate the durable identifiers (repo, branch, IDs, URLs) and "
            "confirm the goal still matches what the user last asked. Never let a checkpoint, "
            "split, or re-anchor interrupt an irreversible step mid-flight - finish the current "
            "reversible unit first."
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
