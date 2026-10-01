"""Offline integrity gates for the guardian fine-tune TRAINING set
(evals/guardian_finetune_data.py). No model download, no network - CI-safe.

The hard invariant is disjointness from the frozen acceptance set
(evals/guardian_traces.py): training must never see the gate, or the
fine-tuned eval numbers mean nothing.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from evals.guardian_finetune_data import (
    SYNTHETIC_CONNECTOR_TOOLS,
    TRAINING_TRACES,
    to_laya_rows,
    training_traces,
)
from evals.guardian_traces import GOLD_LABELS, RISK_CLASSES, TRACES
from noesek.core.orchestration import CONTROLLER_TOOLS


def test_deterministic():
    a = training_traces()
    b = training_traces()
    assert [t["sha"] for t in a] == [t["sha"] for t in b]
    assert [t["id"] for t in a] == [t["id"] for t in b]


def test_disjoint_from_frozen_acceptance_set():
    frozen = {t["state"] for t in TRACES}
    for t in TRAINING_TRACES:
        assert t["state"] not in frozen, t["id"]


def test_size_and_adversarial_weight():
    # owner direction 2026-09-26: "much, much bigger training set with
    # thousands of things", weighted at the rejection cases
    assert 5000 <= len(TRAINING_TRACES) <= 20000
    counts = Counter(t["gold"] for t in TRAINING_TRACES)
    assert set(counts) == set(GOLD_LABELS)
    assert counts["deny"] >= counts["allow"] * 0.8, counts
    assert counts["escalate"] >= 40, counts


def test_labels_and_risk_classes():
    for t in TRAINING_TRACES:
        assert t["gold"] in GOLD_LABELS
        assert t["risk_class"] in RISK_CLASSES
        assert set(t) >= {"id", "category", "gold", "risk_class", "state", "sha", "note"}


def test_action_first_format():
    for t in TRAINING_TRACES:
        head, _, rest = t["state"].partition("\nreasoning: ")
        assert rest, t["id"]
        assert ": " in head, t["id"]
        assert rest.count("\ncontext: ") == 1, t["id"]
        assert len(t["state"]) <= 2000, t["id"]


def test_unique_states():
    shas = [t["sha"] for t in TRAINING_TRACES]
    assert len(set(shas)) == len(shas)


def test_adversarial_coverage():
    cats = Counter(t["category"] for t in TRAINING_TRACES if t["gold"] == "deny")
    minimums = {"destructive": 100, "exfiltration": 300, "credential_access": 150,
                "injection": 800, "supply_chain": 80, "network_abuse": 40,
                "privacy": 80, "financial": 800, "unsafe_exec": 150}
    for required, minimum in minimums.items():
        assert cats[required] >= minimum, (required, cats[required], minimum)


def test_every_controller_tool_has_historical_or_pending_coverage():
    # owner direction 2026-09-26: "train it for all tools and connectors"
    from evals.guardian_youtube_tools import PENDING_TRACES
    used = {t["state"].split(": ", 1)[0] for t in list(TRAINING_TRACES)+PENDING_TRACES}
    missing = CONTROLLER_TOOLS - used
    assert not missing, f"controller tools with neither historical nor pending trace: {sorted(missing)}"


def test_connector_shape_trained():
    # current connector surfaces and plausible future connectors must both
    # appear, so the guardian learns the shape rather than the registry
    used = {t["state"].split(": ", 1)[0] for t in TRAINING_TRACES}
    for expected in ("slack_read", "telegram_send", "whatsapp_read", "obsidian_read",
                     "notion_read", "notion_write", "todoist_add", "spotify_play",
                     "linear_create_issue", "homeassistant_set_light"):
        assert expected in used, expected


def test_trace_tools_known_or_whitelisted():
    for tr in TRAINING_TRACES:
        tool = tr["state"].split(": ", 1)[0]
        assert tool in CONTROLLER_TOOLS or tool in SYNTHETIC_CONNECTOR_TOOLS, (tr["id"], tool)


def test_escalate_is_not_deny():
    for t in TRAINING_TRACES:
        if t["gold"] == "escalate":
            assert t["note"], t["id"]


def test_no_real_secret_shapes():
    banned = re.compile(r"AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|-----BEGIN|postgres://[^\s]*:[^\s@]+@")
    for t in TRAINING_TRACES:
        assert not banned.search(t["state"]), t["id"]


def test_laya_rows_shape():
    rows = to_laya_rows()
    assert len(rows) == len(TRAINING_TRACES)
    for r in rows[:25]:
        assert set(r) == {"id", "workflow", "state", "questions", "gold"}
        state = json.loads(r["state"])
        assert state.count("\nreasoning: ") == 1
        questions = json.loads(r["questions"])
        gold = json.loads(r["gold"])
        assert set(questions) == {"action_class", "verdict"} == set(gold)
        for qid in gold:
            probs = gold[qid]["probabilities"]
            assert abs(sum(probs.values()) - 1.0) < 1e-9
            assert max(probs.values()) == 1.0  # one-hot


def _mask_action(action: str) -> str:
    """Collapse pool-filled values so one surface template = one shape."""
    import evals.guardian_finetune_data as m
    pools = set()
    for name in dir(m):
        v = getattr(m, name)
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            pools.update(x.lower() for x in v if 2 < len(x) < 60)
    a = action.lower()
    a = re.sub(r"\$\d[\d,]*(\.\d+)?", "$N", a)
    a = re.sub(r"\d+\.\d+|\d+", "N", a)
    a = re.sub(r"~[/\w.\-]*", "PATH", a)
    a = re.sub(r"/[\w.\-/]+", "PATH", a)
    a = re.sub(r"\b[\w.\-]+\.(?:com|net|org|io|example|dev)\b", "DOM", a)
    for p in sorted(pools, key=len, reverse=True):
        a = a.replace(p, "?")
    return re.sub(r"\s+", " ", a).strip()


def test_surface_diversity_no_template_dominance():
    """Owner direction 2026-09-26 (after the 5,748-trace v4 regression):
    diversity of surface forms, not near-copies. v4 collapsed credential
    recall 21/24 -> 10/24 because one command template drowned the varied
    handwritten forms. Assert each key family keeps many distinct masked
    shapes and no single shape exceeds 5% of its family."""
    shapes = {}
    rows = {}
    for t in TRAINING_TRACES:
        cat = t["category"]
        shape = _mask_action(t["state"].split(": ", 1)[1])
        shapes.setdefault(cat, set()).add(shape)
        rows.setdefault(cat, Counter())[shape] += 1
    minimums = {
        "credential_access": 110,
        "financial": 70,
        "injection": 290,
        "exfiltration": 90,
        "destructive": 175,
        "unsafe_exec": 115,
        "supply_chain": 185,
        "network_abuse": 220,
        "privacy": 38,
    }
    for cat, n in minimums.items():
        assert len(shapes[cat]) >= n, (cat, len(shapes[cat]))
    for cat in ("credential_access", "financial", "injection",
                "exfiltration", "destructive"):
        top = rows[cat].most_common(1)[0][1]
        total = sum(rows[cat].values())
        assert top / total <= 0.05, (cat, top, total)
