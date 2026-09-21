"""Prompt optimizer (Ethan's roadmap P5): turn a rough instruction into a
structured prompt. Deterministic heuristics - no extra model call, no deps.

Idea study: nidhinjs/prompt-master (MIT) runs a pipeline - detect the task
type, then apply only safe techniques (role, structure, grounding, format).
This is our own implementation of that pattern, tuned for Noesek's chat use.
"""
import re
from pydantic import BaseModel, Field

class OptimizePromptInput(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000, description="The rough instruction or prompt to tighten")
    target: str = Field(default="general", max_length=60, description="Optional hint: coding, writing, research, data, general")

_TYPES = [
    ("coding", ("code", "function", "script", "bug", "error", "api", "python", "javascript", "sql", "refactor", "test", "deploy")),
    ("writing", ("write", "essay", "email", "blog", "story", "article", "caption", "letter", "rewrite", "draft")),
    ("research", ("research", "compare", "analyz", "investigate", "find out", "sources", "study", "report on")),
    ("data", ("data", "csv", "table", "spreadsheet", "chart", "calculate", "summarize numbers", "metrics")),
]

_FORMATS = {
    "coding": "Working code with a brief explanation of key decisions; note any assumptions.",
    "writing": "The finished piece, matching the requested tone and length; no meta-commentary.",
    "research": "A short synthesis with a source URL per claim, plus a plain list of what could not be verified.",
    "data": "The computed result with the method stated; tables or lists where they help.",
    "general": "A direct answer first, then supporting detail only where needed.",
}

def detect_type(text: str, hint: str = "") -> str:
    hint = (hint or "").strip().lower()
    if hint in _FORMATS and hint != "general":
        return hint
    low = text.lower()
    best, best_hits = "general", 0
    for name, words in _TYPES:
        hits = sum(1 for w in words if w in low)
        if hits > best_hits:
            best, best_hits = name, hits
    return best

def extract_constraints(text: str) -> list[str]:
    """Pull explicit constraints out of the rough text (lengths, deadlines, must/must-not)."""
    out = []
    for m in re.finditer(r"([^.!?\n]*\b(?:must|never|always|only|at most|at least|no more than|under|max|exactly)\b[^.!?\n]*)", text, re.I):
        c = m.group(1).strip(" ,;")
        if 8 < len(c) < 200:
            out.append(c)
    for m in re.finditer(r"\b(\d+\s*(?:words?|sentences?|paragraphs?|pages?|items?|examples?|minutes?|hours?|days?))\b", text, re.I):
        out.append(m.group(1))
    seen, deduped = set(), []
    for c in out:
        k = c.lower()
        if k not in seen:
            seen.add(k); deduped.append(c)
    return deduped[:6]

def optimize_prompt_text(raw: str, target: str = "") -> dict:
    text = raw.strip()
    ttype = detect_type(text, target)
    constraints = extract_constraints(text)
    techniques = ["task-type detection", "structured sections", "output-format specification"]
    if constraints:
        techniques.append("explicit constraint extraction")
    techniques.append("grounding anchor")

    lines = [
        f"## Objective",
        text,
        "",
        "## Approach",
        f"1. Restate the task in one sentence before starting; correct it if the restatement misses the point.",
        f"2. Do the work directly; do not describe doing it.",
        f"3. Check the result against every constraint below before answering.",
        "",
        "## Constraints",
    ]
    if constraints:
        lines += [f"- {c}" for c in constraints]
    else:
        lines.append("- None stated. If a key detail is missing, make the most reasonable assumption and name it.")
    lines += [
        "",
        "## Ground rules",
        "- Use only information in this prompt or fetched from cited sources; do not invent facts.",
        "- If the task cannot be done as stated, say why and give the closest useful result.",
        "",
        "## Output format",
        _FORMATS[ttype],
    ]
    return {
        "detected_type": ttype,
        "optimized_prompt": "\n".join(lines),
        "applied_techniques": techniques,
        "notes": f"Detected task type: {ttype}. Edit the Constraints section if the extraction missed anything.",
    }

async def optimize_prompt(inp: OptimizePromptInput):
    return optimize_prompt_text(inp.prompt, inp.target)
