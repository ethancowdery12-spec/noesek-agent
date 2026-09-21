"""P7: adversarial multi-review reconciliation."""
from noesek.tools.adversarial import (AdversarialReviewInput, Finding,
                                      adversarial_review, review_findings)


def _inp(findings, task_type="code"):
    return AdversarialReviewInput(task_type=task_type,
                                  subject_summary="backup script",
                                  findings=findings)


def test_finding_without_evidence_rejected():
    out = review_findings(_inp([Finding(claim="The loop is slow")]))
    assert out["survivors"] == []
    assert "no concrete evidence" in out["rejected"][0]["reason"]


def test_speculation_rejected():
    out = review_findings(_inp([Finding(claim="Maybe the cache is stale?",
                                        evidence="line 42 of cache.py shows staleness")]))
    assert out["survivors"] == []
    assert "speculation" in out["rejected"][0]["reason"]


def test_evidenced_finding_survives_sorted_by_severity():
    fs = [Finding(claim="Typo in log message", evidence="line 9: 'recieve'", severity="low"),
          Finding(claim="SQL injection", evidence='line 21: f"SELECT * WHERE id={uid}"', severity="high")]
    out = review_findings(_inp(fs))
    assert len(out["survivors"]) == 2
    assert out["survivors"][0]["severity"] == "high"


def test_duplicates_collapse_keep_higher_severity():
    fs = [Finding(claim="Missing timeout on the HTTP call", evidence="line 33 requests.get(url)", severity="low"),
          Finding(claim="HTTP call has no timeout", evidence="line 33: requests.get without timeout=", severity="high")]
    out = review_findings(_inp(fs))
    assert len(out["survivors"]) == 1
    assert out["survivors"][0]["severity"] == "high"
    assert "duplicate" in out["rejected"][0]["reason"]


def test_bad_severity_rejected():
    out = review_findings(_inp([Finding(claim="X", evidence="line 1: x=1", severity="critical")]))
    assert out["survivors"] == []
    assert "severity" in out["rejected"][0]["reason"]


def test_checklist_returned_per_type():
    out = review_findings(_inp([], task_type="research"))
    assert any("sources" in c for c in out["checklist"])
    out2 = review_findings(_inp([], task_type="unknown-type"))
    assert out2["checklist"]


async def test_adversarial_review_handler():
    out = await adversarial_review(_inp([Finding(claim="Off by one", evidence="line 7: range(len(a)+1)", severity="medium")]))
    assert "1 finding(s) survived" in out["verdict"]


def test_adversarial_review_registered_on_controller():
    import inspect
    import noesek.core.controller as C
    assert '"adversarial_review"' in inspect.getsource(C)
