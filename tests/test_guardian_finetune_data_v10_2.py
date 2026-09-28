"""Offline integrity gates for the v10.2 guardian fine-tune set
(evals/guardian_finetune_data_v10_2.py). No model, no network - CI-safe.

v10.2 exists because of the 2026-09-28 live finding: the controller's
empty-reasoning fallback ("no reasoning supplied") appeared in training
only on deny rows, so every tool call the LLM makes without accompanying
prose inherited a deny association (live: arithmetic blocked at 0.60).
The serving fallback is now the neutral sentinel
"User made the request directly; no extra rationale given", and v10.2
trains that sentinel on benign AND malicious rows so the model keys on
the action. The invariants here pin the sentinel families, the v10.1
superset, and the live-shape acceptance additions.
"""
from __future__ import annotations

import json
from collections import Counter

from evals.guardian_finetune_data_v10_1 import TRAINING_TRACES_V10_1 as V101
from evals.guardian_finetune_data_v10_2 import (ACCEPTANCE_TRACES_V10_2,
                                                OLD_SENTINEL, SENTINEL,
                                                TRAINING_TRACES_V10_2,
                                                to_laya_rows, training_traces)
from evals.guardian_traces import GOLD_LABELS, RISK_CLASSES

TRAINING_TRACES = TRAINING_TRACES_V10_2


def _tool(t):
    return t["state"].split(": ", 1)[0]


def _reasoning(t):
    return t["state"].split("\nreasoning: ", 1)[1].split("\ncontext: ", 1)[0]


def test_deterministic():
    assert [t["sha"] for t in training_traces()] == [t["sha"] for t in training_traces()]


def test_labels_valid_and_states_unique():
    shas = [t["sha"] for t in TRAINING_TRACES]
    assert len(set(shas)) == len(shas)
    assert len({t["state"] for t in TRAINING_TRACES}) == len(TRAINING_TRACES)
    for t in TRAINING_TRACES:
        assert t["gold"] in GOLD_LABELS and t["risk_class"] in RISK_CLASSES, t["id"]
        head, _, rest = t["state"].partition("\nreasoning: ")
        assert rest and rest.count("\ncontext: ") == 1, t["id"]
        tool, _, payload = head.partition(": ")
        assert tool and isinstance(json.loads(payload), dict), t["id"]


def test_v101_superset_nothing_removed():
    new_states = {t["state"] for t in TRAINING_TRACES}
    missing = [t["id"] for t in V101 if t["state"] not in new_states]
    assert not missing, f"v10.1 rows dropped: {missing[:5]}"


def test_sentinel_families_present_and_labeled():
    fam = {}
    for t in TRAINING_TRACES:
        if t["category"].startswith("sentinel_") or t["category"] == "agent_voice":
            fam.setdefault(t["category"], []).append(t)
    assert set(fam) == {"sentinel_benign", "sentinel_escalate", "sentinel_deny",
                        "agent_voice"}, dict(Counter(t["category"] for t in TRAINING_TRACES))
    for t in fam["sentinel_benign"]:
        assert _reasoning(t) == SENTINEL and t["gold"] == "allow", t["id"]
    for t in fam["sentinel_escalate"]:
        assert _reasoning(t) == SENTINEL and t["gold"] == "escalate", t["id"]
    for t in fam["sentinel_deny"]:
        assert _reasoning(t) == SENTINEL and t["gold"] == "deny", t["id"]
    for t in fam["agent_voice"]:
        assert t["gold"] == "allow" and _reasoning(t) != SENTINEL, t["id"]
    # the old sentinel never appears on new allow/escalate rows
    for t in TRAINING_TRACES:
        if _reasoning(t) == OLD_SENTINEL:
            assert t["gold"] == "deny", f"old sentinel on non-deny row {t['id']}"


def test_acceptance_additions_held_out():
    train_states = {t["state"] for t in TRAINING_TRACES}
    new_acc = [t for t in ACCEPTANCE_TRACES_V10_2 if t["id"].startswith("fz102-")]
    assert len(new_acc) == 9
    for t in new_acc:
        assert t["state"] not in train_states, f"acceptance leak: {t['id']}"
    by_note = {t["note"].split(":")[0]: t for t in new_acc}
    # the morning's three failure shapes land as allow under the new sentinel
    live = [t for t in new_acc if t["note"].startswith("live miss")]
    assert len(live) == 3 and all(t["gold"] == "allow" for t in live)
    # old-sentinel pins stay deny
    bc = [t for t in new_acc if t["note"].startswith("back-compat")]
    assert len(bc) == 2 and all(t["gold"] == "deny" for t in bc)


def test_laya_rows_shape():
    rows = to_laya_rows()
    assert len(rows) == len(TRAINING_TRACES)
    r = rows[0]
    assert set(r) == {"id", "workflow", "state", "questions", "gold"}
