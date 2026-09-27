"""v7 guardian finetune data: every v6 labeled case re-rendered in the exact
production state format, closing the train/serve format skew the staging
canary exposed on 2026-09-27 (deny_score=1.0 on a benign JSON-shaped probe).

The skew: v6 (19,776 cases) and the frozen set (349) render the action field
as natural language ("calendar_read: list events containing 'x'"), but the
live gate (src/noesek/guardian/scorer.py build_state) json-dumps the
controller's argument dict ("calendar_read: {\"max_results\": 10}"). Zero of
19,776 v6 states matched the production shape, so every real gated call was
out-of-distribution and the published v6 numbers only describe
natural-language traffic.

v7 keeps every v6 case, value, label, and distribution. Only the rendering
changes: each case's action text is mapped into the tool's real argument
fields (field names from the live registry's pydantic schemas, dumped
2026-09-27) and the state is produced by build_state itself, so training and
serving cannot drift again. Cases are derived mechanically from
evals/guardian_finetune_data.TRAINING_TRACES; do not edit v6 - it stays as
the natural-language reference set.
"""
from __future__ import annotations

import hashlib
import re

from noesek.guardian.scorer import build_state

from evals import guardian_finetune_data as v6

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_MONEY_RE = re.compile(r"\$[\d,]+(?:\.\d+)?")
_ORDER_RE = re.compile(r"#\d+")


def _pick(seed_text: str, options: list) -> object:
    """Deterministic pseudo-random choice so regeneration is stable."""
    h = int(hashlib.sha256(seed_text.encode()).hexdigest(), 16)
    return options[h % len(options)]


def _code_arg(action: str) -> str:
    m = _BACKTICK_RE.search(action)
    return m.group(1) if m else action


def _to_arg(action: str) -> str:
    m = _EMAIL_RE.search(action)
    if m:
        return m.group(0)
    m = re.search(r"\bto ([A-Z][a-z]+)\b", action)
    if m:
        return m.group(1)
    m = re.search(r"\bthe ([\w -]{3,30}?)(?:\s+(?:with|about|for|per|as)\b|$)", action)
    return m.group(1) if m else "the requested recipient"


# Per-tool argument renderers: v6 action text -> production-shaped argument
# dict. Field names come from the live registry's input models where the tool
# is registered; connector and foreign tools use their conventional fields.
# The goal is format fidelity (JSON args, real keys, values in the right
# fields), not full schema coverage - production itself sends sparse dicts.


def _r_simple(field):
    return lambda tool, action: {field: action}


def _r_empty(tool, action):
    return {}


def _r_max_results(tool, action):
    return {"max_results": _pick(action, [10, 20, 50])}


def _r_code_interpreter(tool, action):
    args = {"code": _code_arg(action)}
    if action.startswith(("run ", "execute ")):
        args = {"action": "run", **args}
    return args


def _r_code_act(tool, action):
    return {"task": action, "code": _code_arg(action) if "`" in action else "# derived at runtime"}


def _r_calc(tool, action):
    return {"expression": _code_arg(action)}


def _r_date_math(tool, action):
    return {"op": "shift", "date": "2026-09-27", "other_date": _code_arg(action)}


def _r_exact_solve(tool, action):
    return {"goal": action, "code": _code_arg(action)}


def _r_duckdb(tool, action):
    return {"query": _code_arg(action)}


def _r_gmail_send(tool, action):
    return {"to": _to_arg(action), "subject": _pick(action, ["update", "notes", "follow-up"]),
            "body": action}


def _r_msg_send(field):
    def r(tool, action):
        return {field: _to_arg(action), "text": action}
    return r


def _r_slack_send(tool, action):
    ch = "#general"
    m = re.search(r"(#[\w-]+)", action)
    if m:
        ch = m.group(1)
    return {"channel": ch, "text": action}


def _r_calendar_write(tool, action):
    return {"title": action, "when": _pick(action, ["Thursday 6pm", "next Monday 9am", "Oct 12 2pm"])}


def _r_create_file(tool, action):
    m = re.search(r"([\w./-]+\.\w{1,5})\b", action)
    name = m.group(1) if m else "notes/output.md"
    return {"name": name, "content": action}


def _r_money(field_amount="amount", field_to="to"):
    def r(tool, action):
        m = _MONEY_RE.search(action)
        args = {field_amount: m.group(0) if m else "$100", field_to: _to_arg(action)}
        return args
    return r


def _r_crypto(tool, action):
    m = re.search(r"([\d.]+)\s*BTC", action)
    return {"amount_btc": m.group(1) if m else "0.1", "address": "bc1q..." + action[-8:]}


def _r_refund(tool, action):
    m = _ORDER_RE.search(action)
    return {"charge_id": "ch_" + (m.group(0)[1:] if m else "1042"), "amount": "full"}


def _r_order(tool, action):
    m = _MONEY_RE.search(action)
    return {"action": "reorder", "total": m.group(0) if m else "$50", "payment": "stored card"}


def _r_payroll(tool, action):
    return {"period": "current", "note": action}


def _r_lock(tool, action):
    return {"lock": "front_door", "note": action}


def _r_alarm(tool, action):
    return {"zone": "perimeter", "note": action}


def _r_light(tool, action):
    return {"entity": "light.bedroom", "brightness_pct": _pick(action, [20, 50, 100])}


def _r_spotify_play(tool, action):
    return {"query": action, "device": "living-room speaker"}


def _r_linkedin(tool, action):
    if action.startswith(("read", "show", "get", "check")):
        return {"action": "profile"}
    return {"action": "share", "text": action, "visibility": "PUBLIC"}


def _r_browser_cookies(tool, action):
    m = re.search(r"([\w-]+\.\w{2,})", action)
    domain = m.group(1) if m else "github.com"
    if action.startswith(("read", "export", "dump", "show the stored", "fetch the stored")):
        return {"action": "export", "domain": domain}
    return {"action": "status", "domain": domain}


def _r_switch_model(tool, action):
    if action.startswith(("disable", "enable", "turn off", "turn on")):
        return {"model": action}  # not a model name at all - that IS the anomaly
    return {"model": _pick(action, ["deepseek-chat", "gpt-4o-mini", "default"])}


def _r_forget(tool, action):
    return {"memory_id": _pick(action, [7, 12, 42, 108])}


def _r_supersede(tool, action):
    return {"memory_id": 7, "content": action}


def _r_memory_get(tool, action):
    return {"ids": [_pick(action, [3, 7, 12, 42])]}


def _r_create_task(tool, action):
    return {"title": action, "run_in_seconds": _pick(action, [3600, 43200, 86400])}


def _r_delegate(tool, action):
    return {"worker": "worker-1", "instruction": action}


def _r_office_doc(tool, action):
    m = re.search(r"(\.\w{2,5})\b", action)
    ext = m.group(1) if m else ".xlsx"
    return {"action": "create", "file": f"workspace-output{ext}", "path": action}


def _r_import(field="file"):
    def r(tool, action):
        m = re.search(r"([\w./-]+\.\w{2,5})\b", action)
        return {field: m.group(1) if m else action}
    return r


def _r_page(field_page, field_text=None):
    def r(tool, action):
        args = {field_page: action}
        if field_text:
            args[field_text] = action
        return args
    return r


def _r_drive_share(tool, action):
    return {"path": action, "role": "viewer", "note": action}


def _r_github_write(tool, action):
    m = re.search(r"(PR #\d+|pull request #?\d+)", action)
    return {"repo": "user/project", "pr": m.group(1) if m else "PR #1", "body": action}


def _r_twitter(tool, action):
    return {"text": action}


def _r_shopify(tool, action):
    return _r_order(tool, action)


_RENDERERS = {
    # memory
    "recall": _r_simple("query"), "remember": _r_simple("content"),
    "memory_get": _r_memory_get, "forget": _r_forget, "supersede_memory": _r_supersede,
    # reads
    "gmail_read": _r_max_results, "calendar_read": _r_max_results,
    "github_notifications": _r_max_results, "github_read": _r_empty,
    "slack_read": lambda t, a: {"channel": "#general"},
    "telegram_read": lambda t, a: {"chat": "family"},
    "whatsapp_read": lambda t, a: {"chat": _pick(a, ["contractor", "family group"])},
    "discord_read": lambda t, a: {"channel": "#announcements"},
    "notion_read": _r_page("page"), "obsidian_read": _r_import("path"),
    "drive_read": _r_import("path"), "linear_read": _r_empty, "trello_read": lambda t, a: {"board": "Sprint"},
    "todoist_list": _r_empty, "strava_read": lambda t, a: {"days": 7},
    "oura_read": _r_empty, "garmin_sync": lambda t, a: {"days": 7},
    "spotify_current": _r_empty, "homeassistant_status": _r_empty,
    "camera_snapshot": lambda t, a: {"camera": "doorbell"},
    "fitness_query": lambda t, a: {"days": _pick(a, [7, 30, 90])},
    # compute
    "code_interpreter": _r_code_interpreter, "code_act": _r_code_act,
    "calc": _r_calc, "date_math": _r_date_math, "exact_solve": _r_exact_solve,
    "duckdb_query": _r_duckdb, "test_verifier": lambda t, a: {"path": "tests/", "pytest_args": "-q"},
    # files/creative/analysis
    "create_file": _r_create_file, "office_doc": _r_office_doc,
    "story_critique": _r_simple("story"), "generate_variants": lambda t, a: {"task": a, "n": 3},
    "humanize": _r_simple("text"), "rewrite_natural": _r_simple("text"),
    "optimize_prompt": _r_simple("prompt"), "scrub": _r_simple("text"),
    "speak": _r_simple("text"), "handoff": _r_simple("content"),
    "seo_audit": _r_simple("html"), "geo_audit": _r_simple("html"),
    "code_graph": _r_simple("query"), "code_intel": lambda t, a: {"action": "search", "query": a},
    "code_review": lambda t, a: {"staged": True},
    "adversarial_review": _r_simple("subject_summary"),
    "security_audit": lambda t, a: {"root": "."},
    "literature_search": _r_simple("query"), "skill_library": lambda t, a: {"action": "list", "query": a},
    "playbook": lambda t, a: {"action": "get", "name": a},
    "design_system": lambda t, a: {"action": "check", "checklist": a},
    "library_docs": lambda t, a: {"library": "httpx", "question": a},
    "search_tools": _r_simple("query"),
    # tasks
    "list_tasks": _r_empty, "create_task": _r_create_task, "cancel_task": lambda t, a: {"task_id": 3},
    "switch_model": _r_switch_model, "delegate_task": _r_delegate,
    # imports
    "ofx_import": _r_import(), "fit_import": _r_import(), "receipt_import": _r_import(),
    # communication
    "gmail_send": _r_gmail_send, "slack_send": _r_slack_send,
    "telegram_send": _r_msg_send("to"), "whatsapp_send": _r_msg_send("to"),
    "discord_send": _r_msg_send("channel"), "twitter_post": _r_twitter,
    "linkedin": _r_linkedin, "github_write": _r_github_write,
    # writes / devices / money
    "calendar_write": _r_calendar_write,
    "notion_write": _r_page("page", "text"), "obsidian_write": _r_page("path", "text"),
    "todoist_add": _r_simple("content"), "trello_add_card": lambda t, a: {"board": "Sprint", "title": a},
    "linear_create_issue": _r_simple("title"),
    "spotify_play": _r_spotify_play, "homeassistant_set_light": _r_light,
    "smart_lock_unlock": _r_lock, "alarm_disable": _r_alarm,
    "drive_share": _r_drive_share, "browser_cookies": _r_browser_cookies,
    "bank_transfer": _r_money(), "crypto_send": _r_crypto,
    "stripe_refund": _r_refund, "shopify_order": _r_shopify, "payroll_run": _r_payroll,
}


def _split_v6_state(state: str):
    head, rline, cline = state.split("\n")
    tool, action = head.split(": ", 1)
    return tool, action, rline[len("reasoning: "):], cline[len("context: "):]


def _render(tool: str, action: str) -> dict:
    fn = _RENDERERS.get(tool)
    if fn is None:
        return {"input": action}
    return fn(tool, action)


def _convert(item: dict) -> dict:
    tool, action, reasoning, context = _split_v6_state(item["state"])
    args = _render(tool, action)
    return {**item, "state": build_state(tool, args, reasoning, context)}


TRAINING_TRACES = [_convert(it) for it in v6.TRAINING_TRACES]


# ---------------------------------------------------------------------------
# kernel interface (mirrors v6: same row shape, fresh ids/shas for v7 states)

_DIRECT_ONEHOT = {"allow": "approve", "deny": "deny", "escalate": "escalate"}


def _finalize():
    out = []
    seen = set()
    for t in TRAINING_TRACES:
        # v6 dedupes identical states; v7 must dedupe again because distinct
        # natural-language actions can collapse to the same JSON args
        # (e.g. two gmail_read phrasings -> {"max_results": 20}).
        if t["state"] in seen:
            continue
        seen.add(t["state"])
        t["id"] = f"ft7-{len(out):05d}"
        t["sha"] = hashlib.sha256(t["state"].encode()).hexdigest()[:12]
        out.append(t)
    return out


TRAINING_TRACES = _finalize()


def training_traces() -> list[dict]:
    """Same contract as v6: deterministic set (v6 is itself deterministic and
    the v7 render is pure, so this module-level build is the canonical set)."""
    return list(TRAINING_TRACES)


def to_laya_rows(traces=None) -> list[dict]:
    """Identical row shape to v6 so the finetune kernel's preprocessing works
    unchanged - only the state format (JSON args) differs."""
    import json as _json
    from evals.guardian_eval import DIRECT_QUESTION, RISK_QUESTION
    rows = []
    for t in traces if traces is not None else TRAINING_TRACES:
        risk_gold = {k: 0.0 for k in v6.RISK_CLASSES}
        risk_gold[t["risk_class"]] = 1.0
        direct_gold = {k: 0.0 for k in DIRECT_QUESTION["verdict"]["criteria"]}
        direct_gold[_DIRECT_ONEHOT[t["gold"]]] = 1.0
        rows.append({
            "id": t["id"],
            "workflow": t["category"],
            "state": _json.dumps(t["state"]),
            "questions": _json.dumps({"action_class": RISK_QUESTION["action_class"],
                                      "verdict": DIRECT_QUESTION["verdict"]}),
            "gold": _json.dumps({"action_class": {"probabilities": risk_gold},
                                 "verdict": {"probabilities": direct_gold}}),
        })
    return rows


if __name__ == "__main__":
    from collections import Counter
    counts = Counter(t["gold"] for t in TRAINING_TRACES)
    print(f"{len(TRAINING_TRACES)} v7 training traces | gold: {dict(counts)}")
