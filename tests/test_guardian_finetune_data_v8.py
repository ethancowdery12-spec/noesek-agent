"""Offline integrity gates for the v8 guardian fine-tune set
(evals/guardian_finetune_data_v8.py). No model, no network - CI-safe.

v8 exists because of the 2026-09-27 live banding failure: v7 had every chat
tool COVERED but taught 95% deny on code_interpreter and 81% deny / 0 allow
on gmail_send, so benign compute escalated and a benign self-email denied at
1.00. The invariants here are therefore DISTRIBUTIONAL: every live-registry
tool must be covered (checked against the real Controller registry, not a
hand-maintained list), high-traffic tools must carry meaningful benign mass,
the mangled gmail_send rows must be gone, and the acceptance gate must test
benign traffic on the previously skewed tools.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from evals.guardian_finetune_data_v8 import (ACCEPTANCE_TRACES_V8, TRAINING_TRACES,
                                             to_laya_rows, training_traces)
from evals.guardian_traces import GOLD_LABELS, RISK_CLASSES


def _tool(t):
    return t["state"].split(": ", 1)[0]


def test_deterministic():
    assert [t["sha"] for t in training_traces()] == [t["sha"] for t in training_traces()]


def test_every_state_action_is_json():
    for t in TRAINING_TRACES:
        head, _, rest = t["state"].partition("\nreasoning: ")
        assert rest and rest.count("\ncontext: ") == 1, t["id"]
        tool, _, payload = head.partition(": ")
        assert tool and payload, t["id"]
        assert isinstance(json.loads(payload), dict), t["id"]
        assert len(t["state"]) <= 2000, t["id"]


def test_unique_states():
    shas = [t["sha"] for t in TRAINING_TRACES]
    assert len(set(shas)) == len(shas)
    assert len({t["state"] for t in TRAINING_TRACES}) == len(TRAINING_TRACES)


def test_labels_valid():
    for t in TRAINING_TRACES:
        assert t["gold"] in GOLD_LABELS and t["risk_class"] in RISK_CLASSES, t["id"]
        assert set(t) >= {"id", "category", "gold", "risk_class", "state", "note"}


def test_size_and_gold_balance():
    assert 12000 <= len(TRAINING_TRACES) <= 30000
    counts = Counter(t["gold"] for t in TRAINING_TRACES)
    assert set(counts) == set(GOLD_LABELS)
    assert counts["allow"] >= 3000, counts   # v7 had 2,905 - rebalance adds ~1.7k
    assert counts["escalate"] >= 1000, counts


def test_every_live_registry_tool_has_historical_or_pending_coverage():
    # THE v8 invariant: coverage measured against the REAL controller registry,
    # not a hand-maintained list (the stale-list blind spot that hid the skew).
    from finetune.dump_tools import production_specs
    live = {s.name for s in production_specs()}
    # Historical trained set stays frozen. Registry additions require explicit
    # schema-valid pending fixtures, not a claim the deployed model learned them.
    from evals.guardian_youtube_tools import PENDING_TRACES
    used = {_tool(t) for t in list(TRAINING_TRACES) + PENDING_TRACES}
    missing = live - used
    assert not missing, f"live tools with neither historical nor pending trace: {sorted(missing)}"


def test_skew_rebalanced():
    by_tool = {}
    for t in TRAINING_TRACES:
        by_tool.setdefault(_tool(t), Counter())[t["gold"]] += 1
    ci = by_tool["code_interpreter"]
    assert ci["allow"] >= 1500, dict(ci)          # was 259 (2.8%) in v7
    assert ci["allow"] / sum(ci.values()) >= 0.12
    gs = by_tool["gmail_send"]
    assert gs["escalate"] >= 700, dict(gs)        # was 432, mostly mangled
    cf = by_tool["create_file"]
    assert cf["allow"] >= 250, dict(cf)           # was 42
    for thin in ("office_doc", "test_verifier", "code_act"):
        assert sum(by_tool[thin].values()) >= 20, (thin, dict(by_tool[thin]))


def test_gmail_benign_rows_wellformed():
    # the 308 renderer-mangled benign gmail_send rows must be gone, and the
    # replacements must have real recipients
    for t in TRAINING_TRACES:
        if _tool(t) == "gmail_send" and t["risk_class"] == "external_communication":
            args = json.loads(t["state"].split("\n", 1)[0].split(": ", 1)[1])
            to = args.get("to", "")
            assert to and not to.startswith("the "), (t["id"], to)
            assert to != "the requested recipient", t["id"]


def test_no_real_secret_shapes():
    banned = re.compile(r"AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|-----BEGIN|postgres://[^\s]*:[^\s@]+")
    for t in TRAINING_TRACES:
        assert not banned.search(t["state"]), t["id"]


def test_adversarial_coverage_kept():
    cats = Counter(t["category"] for t in TRAINING_TRACES if t["gold"] == "deny")
    minimums = {"destructive": 100, "exfiltration": 300, "credential_access": 150,
                "injection": 800, "supply_chain": 80, "network_abuse": 40,
                "privacy": 80, "financial": 800, "unsafe_exec": 150}
    for required, minimum in minimums.items():
        assert cats[required] >= minimum, (required, cats[required], minimum)


def test_laya_rows_shape():
    rows = to_laya_rows()
    assert len(rows) == len(TRAINING_TRACES)
    for r in rows[:25]:
        assert set(r) == {"id", "workflow", "state", "questions", "gold"}
        state = json.loads(r["state"])
        assert state.count("\nreasoning: ") == 1
        json.loads(state.split("\n", 1)[0].split(": ", 1)[1])
        questions = json.loads(r["questions"])
        gold = json.loads(r["gold"])
        assert set(questions) == {"action_class", "verdict"} == set(gold)
        for qid in gold:
            probs = gold[qid]["probabilities"]
            assert abs(sum(probs.values()) - 1.0) < 1e-9
            assert max(probs.values()) == 1.0


def test_acceptance_gate_v8():
    assert 340 <= len(ACCEPTANCE_TRACES_V8) <= 450
    counts = Counter(t["gold"] for t in ACCEPTANCE_TRACES_V8)
    assert counts["allow"] >= 140 and counts["deny"] >= 110 and counts["escalate"] >= 45
    train_states = {t["state"] for t in TRAINING_TRACES}
    for t in ACCEPTANCE_TRACES_V8:
        assert t["state"] not in train_states, t["id"]
        payload = t["state"].split("\n", 1)[0].split(": ", 1)[1]
        assert isinstance(json.loads(payload), dict), t["id"]
    # the gate must now test BENIGN traffic on the previously skewed tools
    by_tool = {}
    for t in ACCEPTANCE_TRACES_V8:
        by_tool.setdefault(_tool(t), Counter())[t["gold"]] += 1
    assert by_tool["code_interpreter"]["allow"] >= 25, dict(by_tool["code_interpreter"])
    assert by_tool["gmail_send"]["escalate"] >= 20, dict(by_tool["gmail_send"])
    assert by_tool["create_file"]["allow"] >= 4, dict(by_tool["create_file"])
