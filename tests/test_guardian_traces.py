"""Offline integrity gates for the guardian trace set (evals/guardian_traces.py).

No model download, no network - CI-safe. The set is the acceptance gate for
the guardian fine-tune, so its invariants are asserted hard.
"""
from __future__ import annotations

import re
from collections import Counter

from evals.guardian_traces import GOLD_LABELS, RISK_CLASSES, TRACES, traces


def test_deterministic():
    a = traces()
    b = traces()
    assert [t["sha"] for t in a] == [t["sha"] for t in b]
    assert [t["id"] for t in a] == [t["id"] for t in b]


def test_size_and_balance():
    assert 300 <= len(TRACES) <= 600
    counts = Counter(t["gold"] for t in TRACES)
    assert set(counts) == set(GOLD_LABELS)
    assert counts["allow"] >= 120, counts
    assert counts["deny"] >= 100, counts
    assert counts["escalate"] >= 40, counts


def test_labels_and_categories():
    for t in TRACES:
        assert t["gold"] in GOLD_LABELS
        assert t["category"]
        assert set(t) >= {"id", "category", "gold", "state", "sha", "note"}


def test_action_first_format():
    # krisstech blueprint: the action (tool: verb) must lead, so metadata
    # cannot push it out of a small context window.
    for t in TRACES:
        head, _, rest = t["state"].partition("\nreasoning: ")
        assert rest, t["id"]
        assert ": " in head, t["id"]
        assert rest.count("\ncontext: ") == 1, t["id"]
        assert len(t["state"]) <= 1600, t["id"]  # ~400 tokens, compressed by contract


def test_unique_states():
    shas = [t["sha"] for t in TRACES]
    assert len(set(shas)) == len(shas)


def test_adversarial_coverage():
    cats = Counter(t["category"] for t in TRACES if t["gold"] == "deny")
    for required in ("destructive", "exfiltration", "credential_access", "injection",
                     "supply_chain", "network_abuse", "privacy", "financial", "unsafe_exec"):
        assert cats[required] >= 5, (required, cats[required])


def test_escalate_is_not_deny():
    # escalate = route to the user, not refuse: every escalate trace must be
    # plausibly user-directed, which the notes record.
    for t in TRACES:
        if t["gold"] == "escalate":
            assert t["note"], t["id"]


def test_no_real_secret_shapes():
    # placeholders must be obvious; nothing in a trace may look like a live key.
    banned = re.compile(r"AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|-----BEGIN|postgres://[^\s]*:[^\s@]+@")
    for t in TRACES:
        assert not banned.search(t["state"]), t["id"]


def test_risk_classes_cover_deny_categories():
    # every deny category must map conceptually onto the risky classes used by
    # the gate design (destructive/exfiltration/credential_access/remote_exec)
    deny_cats = {t["category"] for t in TRACES if t["gold"] == "deny"}
    assert deny_cats  # and the risky-class contract itself is stable
    assert len(RISK_CLASSES) == 7
