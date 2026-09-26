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
    # owner direction 2026-09-26: weight the rejection cases
    assert 600 <= len(TRAINING_TRACES) <= 2500
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
    for required in ("destructive", "exfiltration", "credential_access", "injection",
                     "supply_chain", "network_abuse", "privacy", "financial", "unsafe_exec"):
        assert cats[required] >= 12, (required, cats[required])


def test_every_controller_tool_trained():
    # owner direction 2026-09-26: "train it for all tools and connectors"
    used = {t["state"].split(": ", 1)[0] for t in TRAINING_TRACES}
    missing = CONTROLLER_TOOLS - used
    assert not missing, f"controller tools with no training trace: {sorted(missing)}"


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
