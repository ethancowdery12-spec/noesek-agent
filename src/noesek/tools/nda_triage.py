"""Own-code NDA pre-screen: GREEN / YELLOW / RED with the exact sentences behind each flag.

The screening criteria (mutual vs one-way, standard carve-outs, term, no
non-solicit / non-compete / residuals / liquidated damages) follow the public
NDA triage checklist in anthropics/knowledge-work-plugins (Apache-2.0); this is
a fresh keyword implementation, no text copied. It is a heuristic screen, not
legal advice: it reads the text you give it, quotes what it matched, and says
"not found" rather than guessing. Nothing is sent, signed or shared.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field


class NdaTriageInput(BaseModel):
    text: str = Field(min_length=20, max_length=200000, description="the NDA text")
    we_are: str = Field(default="either", description="either | discloser | recipient: which side the owner is on")
    max_term_years: int = Field(default=5, ge=1, le=30, description="longest confidentiality term the owner accepts")


CARVEOUTS = {
    "public": r"publicly available|public domain|becomes? (?:generally )?(?:known|public)",
    "prior_possession": r"already (?:known|in (?:its|the receiving party's) possession)|prior to (?:the )?disclosure|previously known",
    "independent": r"independently (?:developed|created)",
    "third_party": r"(?:rightfully )?(?:received|obtained) from (?:a )?third party|from a third party",
    "legal_compulsion": r"required by law|compelled|subpoena|court order|legal process|regulat(?:ion|ory) requirement",
}
RED = {
    "non_compete": r"non-?compet|shall not (?:engage in|compete)|not (?:to )?compete",
    "non_solicit": r"non-?solicit|shall not (?:directly or indirectly )?solicit|not (?:to )?(?:solicit|hire)\b",
    "exclusivity": r"exclusiv(?:e|ity) (?:dealing|negotiat|relationship)|shall not (?:enter|engage) in (?:similar )?(?:discussions|negotiations) with",
    "liquidated_damages": r"liquidated damages|penalty of \$|shall pay.{0,40}per (?:breach|violation|day)",
    "residuals": r"residuals?|retained in (?:the )?unaided memor",
    "ip_assignment_or_license": r"hereby assigns?|grants? (?:to )?(?:the )?(?:receiving party|recipient).{0,40}licen[sc]e",
}
YELLOW = {
    "perpetual": r"in perpetuity|perpetual|indefinite(?:ly)?|survive indefinitely",
    "overbroad_definition": r"all information (?:of any kind )?(?:whether or not|regardless of whether).{0,40}(?:marked|designated|labeled)|any and all information",
    "one_sided_remedies": r"(?:receiving|disclosing) party (?:shall|agrees to) (?:reimburse|indemnify)",
    "sworn_certification": r"affidavit|sworn",
    "foreign_or_odd_law": r"governed by the laws? of (?!the state of (?:new york|delaware|california|texas|washington|illinois|massachusetts|florida))",
}


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])", flat) if s.strip()]


def _hits(sents, pattern):
    rx = re.compile(pattern, re.I)
    return [s[:300] for s in sents if rx.search(s)]


def _years(sents):
    out = []
    for s in sents:
        if re.search(r"surviv|term|period|years?", s, re.I):
            for m in re.finditer(r"\b(\d{1,2}|one|two|three|four|five|six|seven|ten)\s*(?:\(\d+\)\s*)?years?\b", s, re.I):
                w = m.group(1).lower()
                n = int(w) if w.isdigit() else {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}[w]
                out.append({"years": n, "sentence": s[:300]})
    return out


def nda_triage(inp: NdaTriageInput) -> dict:
    sents = _sentences(inp.text)
    low = inp.text.lower()
    if not re.search(r"confidential", low):
        return {"ok": False, "error": "text does not mention confidential information; not an NDA or incomplete",
                "executed": False}
    mutual = bool(re.search(r"mutual|each party|either party|the disclosing party and the receiving party", low))
    one_way = bool(re.search(r"\"?(?:the )?(?:company|discloser)\"? (?:will|may) disclose|unilateral|one-way", low))
    kind = "mutual" if mutual and not one_way else ("unilateral" if one_way and not mutual else "unclear")
    red = {k: h for k, p in RED.items() if (h := _hits(sents, p))}
    yellow = {k: h for k, p in YELLOW.items() if (h := _hits(sents, p))}
    carve = {k: bool(_hits(sents, p)) for k, p in CARVEOUTS.items()}
    missing = sorted(k for k, v in carve.items() if not v)
    terms = _years(sents)
    longest = max((t["years"] for t in terms), default=None)
    notes = []
    if longest is None and "perpetual" not in yellow:
        notes.append("no term in years found; check the term and survival clauses by hand")
    if longest is not None and longest > inp.max_term_years:
        yellow["term_over_limit"] = [t["sentence"] for t in terms if t["years"] == longest][:2]
    if kind == "unilateral" and inp.we_are == "recipient":
        yellow["one_way_binds_us"] = ["NDA appears one-way and the owner is the recipient"]
    if kind == "unclear":
        notes.append("could not tell mutual from one-way")
    if not _hits(sents, r"governed by|governing law"):
        notes.append("no governing law clause found")
    if missing:
        yellow["missing_carveouts"] = [f"not found: {m}" for m in missing]
    rating = "RED" if red else ("YELLOW" if yellow else "GREEN")
    route = {"GREEN": "standard approval path", "YELLOW": "counsel review of the flagged clauses",
             "RED": "full legal review before anyone signs"}[rating]
    return {"ok": True, "rating": rating, "route": route, "type": kind, "longest_term_years": longest,
            "red_flags": red, "yellow_flags": yellow, "carveouts_found": carve, "notes": notes,
            "executed": False,
            "caveat": "Keyword screen over the text provided, not legal advice. GREEN is not approval: a qualified person decides, and nothing is signed or sent from here."}
