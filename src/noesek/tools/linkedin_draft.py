"""LinkedIn draft-first pack (owner-requested build; sergebulaev/linkedin-skills, MIT).

Own implementation of the useful parts of the 11-skill bundle, with the
Publora publishing and Apify scraping backends deliberately left out. This
tool never posts, comments, reacts or touches the network: it parses URLs,
lints drafts against the bundle's voice rules, offers hook structures, plans a
posting week, and renders an approval card that says NOT POSTED. Publishing
stays in the separate approval-gated `linkedin` tool.

Not implemented on purpose: AI-detector scoring and "watermark" removal. The
bundle's humanizer claims about fooling detectors are unverified, so lint here
only reports concrete style problems the writer can fix.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

BLACKLIST = ("leverage", "utilize", "facilitate", "streamline", "robust", "seamless", "delve",
             "unlock", "harness", "foster", "cultivate", "landscape", "ecosystem", "paradigm",
             "realm", "tapestry", "game-changer", "deep dive", "at the end of the day",
             "in today's fast-paced world", "it's not just")
BAD_OPENERS = ("this.", "100%", "couldn't agree more", "great insight", "love this", "so true")
LIMITS = {"post": 3000, "comment": 1250, "reply": 1250}
SOFT_RANGE = {"comment": (200, 350)}

HOOKS = {
    "odd_precision_ledger": "Open with an exact, specific number list (costs, hours, counts) that invites a screenshot.",
    "year_over_year_pivot": "Contrast what you believed a year ago with what you do now, with one concrete change.",
    "time_anchor_confession": "Start with a dated admission: 'In March I shipped X and it failed because Y'.",
    "contrarian_with_receipts": "State a view against the default, back it in the next line with a named, checkable example.",
    "curiosity_gap_teaser": "Promise one specific result and withhold the mechanism until line three.",
    "permission_slip": "Tell the reader a thing they are allowed to stop doing, and why.",
    "controlled_ab_anecdote": "Two cases that differ in one variable; show which outcome followed.",
    "false_binary_dissolve": "Name the either-or people argue about, then show the third option with an example.",
}

PILLARS = {"general": ["Lessons", "Behind the scenes", "Opinion", "Proof", "Question"],
           "founder": ["Conviction", "Building in public", "The math", "Proof", "Question"]}

_URL = re.compile(r"https?://(?:www\.)?linkedin\.com/(?P<path>[^\s?#]+)", re.I)


class LinkedInDraftInput(BaseModel):
    action: str = Field(description="parse_url | lint | hooks | plan_week | card")
    kind: str = Field(default="post", description="post | comment | reply")
    text: str = Field(default="", max_length=6000)
    url: str = Field(default="", max_length=500, description="parse_url/card: the LinkedIn post URL")
    founder: bool = Field(default=False, description="plan_week: use the founder pillar set")
    topics: list[str] = Field(default_factory=list, max_length=7, description="plan_week: topics to place")


def parse_url(url: str) -> dict:
    m = _URL.match(url.strip())
    if not m:
        return {"error": "not a linkedin.com URL"}
    path = m.group("path")
    urn = re.search(r"urn:li:(activity|share|ugcPost):(\d+)", url)
    act = re.search(r"activity[-:](\d{10,})", path)
    comment = re.search(r"commentUrn=([^&\s]+)", url)
    if urn:
        post = {"urn": urn.group(0), "id": urn.group(2)}
    elif act:
        post = {"urn": f"urn:li:activity:{act.group(1)}", "id": act.group(1)}
    else:
        return {"error": "no post id found in URL", "path": path}
    return {"post": post, "comment_ref": comment.group(1) if comment else None}


def lint(kind: str, text: str) -> dict:
    kind = kind.strip().lower()
    if kind not in LIMITS:
        return {"error": f"unknown kind '{kind}'", "kinds": sorted(LIMITS)}
    low, issues = text.lower(), []

    def add(rule, detail):
        issues.append({"rule": rule, "detail": detail})

    if len(text) > LIMITS[kind]:
        add("length", f"{len(text)} chars; {kind} limit is {LIMITS[kind]}")
    if kind in SOFT_RANGE and not SOFT_RANGE[kind][0] <= len(text) <= SOFT_RANGE[kind][1]:
        add("length-target", f"bundle target for a {kind} is {SOFT_RANGE[kind][0]}-{SOFT_RANGE[kind][1]} chars (heuristic)")
    words = max(1, len(text.split()))
    dashes = text.count("\u2014")
    if dashes > max(1, round(words / 100)):
        add("em-dash-density", f"{dashes} em dashes in {words} words; keep to about 1 per 100")
    hits = [w for w in BLACKLIST if w in low]
    if hits:
        add("vocabulary", "avoid: " + ", ".join(hits))
    if any(low.lstrip().startswith(o) for o in BAD_OPENERS):
        add("opener", "generic opener; start with a specific detail")
    if low.rstrip().endswith("what do you think?"):
        add("dead-prompt", "ends with 'What do you think?'; ask something specific or land cleanly")
    tags = len(re.findall(r"(?<!\w)#\w+", text))
    if kind != "post" and tags:
        add("hashtags", f"{tags} hashtag(s) in a {kind}; none recommended")
    if kind == "post" and tags > 5:
        add("hashtags", f"{tags} hashtags; 5 or fewer")
    if kind == "post":
        first = text.strip().split("\n", 1)[0]
        if len(first) > 210:
            add("hook-length", f"first line is {len(first)} chars; the feed truncates early (heuristic ~210)")
    if not re.search(r"\d|[A-Z][a-z]+\s[A-Z]|[A-Z]{2,}", text):
        add("specificity", "no number or named entity; add one concrete detail")
    return {"kind": kind, "chars": len(text), "passed": not issues, "issues": issues}


def plan_week(founder: bool, topics: list[str]) -> dict:
    pillars = PILLARS["founder" if founder else "general"]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    plan = [{"day": d, "pillar": p, "topic": topics[i] if i < len(topics) else "(choose a real story or number)"}
            for i, (d, p) in enumerate(zip(days, pillars))]
    return {"plan": plan, "note": "scaffold only; timing advice from the bundle is unverified and not included"}


def linkedin_draft(inp: LinkedInDraftInput) -> dict:
    a = inp.action.strip().lower()
    if a == "parse_url":
        return parse_url(inp.url)
    if a == "lint":
        return lint(inp.kind, inp.text) if inp.text.strip() else {"error": "text is required"}
    if a == "hooks":
        return {"hooks": HOOKS}
    if a == "plan_week":
        return plan_week(inp.founder, inp.topics)
    if a == "card":
        if not inp.text.strip():
            return {"error": "text is required"}
        rep = lint(inp.kind, inp.text)
        if "error" in rep:
            return rep
        target = parse_url(inp.url) if inp.url.strip() else None
        return {"status": "NOT POSTED - draft for your approval", "kind": inp.kind,
                "target": target, "draft": inp.text, "lint": rep,
                "next": "Copy it yourself, or approve it explicitly and use the separate linkedin tool."}
    return {"error": f"unknown action '{inp.action}'",
            "actions": ["parse_url", "lint", "hooks", "plan_week", "card"]}
