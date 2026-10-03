"""Offline integrity gates for the v7 guardian fine-tune set
(evals/guardian_finetune_data_v7.py). No model, no network - CI-safe.

v7 exists because of the train/serve format skew the staging canary exposed
(2026-09-27): production build_state json-dumps tool arguments while v6 and
the frozen set train/eval on natural-language action fields. The hard
invariant here is therefore FORMAT: every v7 state's action field must be a
JSON object - the exact shape the live gate emits - and the labels and
coverage must survive the v6 -> v7 re-rendering.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from evals import guardian_finetune_data as v6
from evals.guardian_finetune_data_v7 import TRAINING_TRACES, to_laya_rows, training_traces
from evals.guardian_traces import GOLD_LABELS, RISK_CLASSES, TRACES
from noesek.core.orchestration import CONTROLLER_TOOLS


def test_deterministic():
    a = [t["sha"] for t in training_traces()]
    b = [t["sha"] for t in training_traces()]
    assert a == b


def test_every_state_action_is_json():
    # THE v7 invariant: production build_state emits json.dumps(arguments);
    # every training state must match that shape exactly.
    for t in TRAINING_TRACES:
        head, _, rest = t["state"].partition("\nreasoning: ")
        assert rest, t["id"]
        assert rest.count("\ncontext: ") == 1, t["id"]
        tool, _, payload = head.partition(": ")
        assert tool and payload, t["id"]
        args = json.loads(payload)
        assert isinstance(args, dict), t["id"]
        assert len(t["state"]) <= 2000, t["id"]


def test_unique_states():
    shas = [t["sha"] for t in TRAINING_TRACES]
    assert len(set(shas)) == len(shas)


def test_size_and_gold_balance():
    assert 5000 <= len(TRAINING_TRACES) <= 20000
    counts = Counter(t["gold"] for t in TRAINING_TRACES)
    assert set(counts) == set(GOLD_LABELS)
    assert counts["deny"] >= counts["allow"] * 0.8, counts
    assert counts["allow"] >= 500, counts  # near-miss allows survive re-rendering
    assert counts["escalate"] >= 40, counts


def test_labels_and_risk_classes():
    for t in TRAINING_TRACES:
        assert t["gold"] in GOLD_LABELS
        assert t["risk_class"] in RISK_CLASSES
        assert set(t) >= {"id", "category", "gold", "risk_class", "state", "sha", "note"}


def test_case_identity_preserved_from_v6():
    # v7 is a re-rendering of v6, not a new set: category/gold/risk_class
    # multisets must match v6's (dedupe may only shrink counts).
    def sig(items):
        return Counter((t["category"], t["gold"], t["risk_class"]) for t in items)
    v7sig = sig(TRAINING_TRACES)
    v6sig = sig(v6.TRAINING_TRACES)
    for key, n7 in v7sig.items():
        assert n7 <= v6sig[key], (key, n7, v6sig[key])
    # and nothing important was lost: at least 85% of v6 cases survive
    assert len(TRAINING_TRACES) >= 0.85 * len(v6.TRAINING_TRACES)


def test_disjoint_from_frozen_acceptance_set():
    frozen = {t["state"] for t in TRACES}
    for t in TRAINING_TRACES:
        assert t["state"] not in frozen, t["id"]


def test_adversarial_coverage():
    cats = Counter(t["category"] for t in TRAINING_TRACES if t["gold"] == "deny")
    minimums = {"destructive": 100, "exfiltration": 300, "credential_access": 150,
                "injection": 800, "supply_chain": 80, "network_abuse": 40,
                "privacy": 80, "financial": 800, "unsafe_exec": 150}
    for required, minimum in minimums.items():
        assert cats[required] >= minimum, (required, cats[required], minimum)


def test_every_controller_tool_has_historical_or_pending_coverage():
    from evals.guardian_youtube_tools import PENDING_TRACES
    used = {t["state"].split(": ", 1)[0] for t in list(TRAINING_TRACES)+PENDING_TRACES}
    missing = CONTROLLER_TOOLS - used
    assert not missing, f"controller tools with no v7 trace: {sorted(missing)}"


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
        json.loads(state.split("\n", 1)[0].split(": ", 1)[1])  # JSON action
        questions = json.loads(r["questions"])
        gold = json.loads(r["gold"])
        assert set(questions) == {"action_class", "verdict"} == set(gold)
        for qid in gold:
            probs = gold[qid]["probabilities"]
            assert abs(sum(probs.values()) - 1.0) < 1e-9
            assert max(probs.values()) == 1.0


def test_acceptance_gate_v7_format_and_disjointness():
    import json as _json
    from evals.guardian_finetune_data_v7 import ACCEPTANCE_TRACES_V7
    assert 300 <= len(ACCEPTANCE_TRACES_V7) <= 349
    counts = Counter(t["gold"] for t in ACCEPTANCE_TRACES_V7)
    assert counts["allow"] >= 120 and counts["deny"] >= 100 and counts["escalate"] >= 40
    train_states = {t["state"] for t in TRAINING_TRACES}
    for t in ACCEPTANCE_TRACES_V7:
        assert t["state"] not in train_states, t["id"]
        payload = t["state"].split("\n", 1)[0].split(": ", 1)[1]
        assert isinstance(_json.loads(payload), dict), t["id"]


def test_acceptance_gate_v7_same_cases_as_frozen():
    # the v7 gate must re-render the SAME frozen cases (comparable numbers),
    # just in production format
    from evals.guardian_finetune_data_v7 import ACCEPTANCE_TRACES_V7
    assert {t["id"][4:] for t in ACCEPTANCE_TRACES_V7} <= {t["id"] for t in TRACES}
