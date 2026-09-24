"""secret_scan gate: clean passes, leaks fail, baseline and pragma honored."""
import json
import sys

import pytest

import scripts.secret_scan as sc

LEAK = 'aws_key = "AKIAIOSFODNN7EXAMPLE"\n'  # pragma: allowlist secret


def _gate(monkeypatch, tmp_path, argv=()):
    monkeypatch.setattr(sc, "BASELINE", tmp_path / ".secrets.baseline")
    monkeypatch.setattr(sys, "argv", ["secret_scan.py", *argv])
    return sc.main()


def _with_files(monkeypatch, files):
    monkeypatch.setattr(sc, "tracked_files", lambda: [str(f) for f in files])


def test_clean_tree_passes(monkeypatch, tmp_path):
    f = tmp_path / "ok.py"; f.write_text("x = 1\n")
    _with_files(monkeypatch, [f])
    (tmp_path / ".secrets.baseline").write_text(json.dumps({"version": "1.5.0", "results": {}}))
    assert _gate(monkeypatch, tmp_path) == 0


def test_leak_fails_with_location(monkeypatch, tmp_path, capsys):
    f = tmp_path / "bad.py"; f.write_text(LEAK)
    _with_files(monkeypatch, [f])
    (tmp_path / ".secrets.baseline").write_text(json.dumps({"version": "1.5.0", "results": {}}))
    assert _gate(monkeypatch, tmp_path) == 1
    assert "bad.py" in capsys.readouterr().out


def test_pragma_suppresses_deliberate_sentinel(monkeypatch, tmp_path):
    f = tmp_path / "ok.py"
    f.write_text(LEAK.rstrip("\n") + "  # pragma: allowlist secret\n")
    _with_files(monkeypatch, [f])
    (tmp_path / ".secrets.baseline").write_text(json.dumps({"version": "1.5.0", "results": {}}))
    assert _gate(monkeypatch, tmp_path) == 0


def test_baselined_finding_passes_then_new_leak_fails(monkeypatch, tmp_path):
    f = tmp_path / "old.py"; f.write_text(LEAK)
    _with_files(monkeypatch, [f])
    assert _gate(monkeypatch, tmp_path, ["--write-baseline"]) == 0  # baseline the reviewed finding
    assert _gate(monkeypatch, tmp_path) == 0                        # known finding passes
    g = tmp_path / "new.py"; g.write_text('token = "ghp_' + "a" * 36 + '"\n')
    _with_files(monkeypatch, [f, g])
    assert _gate(monkeypatch, tmp_path) == 1                        # new finding fails


def test_missing_baseline_is_exit_2(monkeypatch, tmp_path):
    f = tmp_path / "ok.py"; f.write_text("x = 1\n")
    _with_files(monkeypatch, [f])
    assert _gate(monkeypatch, tmp_path) == 2


def test_count_counts_secrets_not_file_pairs():
    from detect_secrets.core.secrets_collection import SecretsCollection
    from detect_secrets.settings import default_settings
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.py")
        with open(p, "w") as fh:
            fh.write(LEAK)
        s = SecretsCollection()
        with default_settings():
            s.scan_file(p)
        assert sc._count(s) == 1  # regression: was items() -> counted 2 per file
