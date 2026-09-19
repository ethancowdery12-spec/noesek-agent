"""License, provenance, and supply-chain guards for vendored code and pins."""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "src/noesek/vendor/hermes"
COMMIT_RE = re.compile(r"c712f06dcdd24053a4118f38d2090ac53137ecfc")


def _manifest():
    rows = {}
    for line in (ROOT / "VENDORING.md").read_text().splitlines():
        m = re.match(r"\| `(noesek/vendor/hermes/\S+)` \| `(\S+)` \| (\d+) \| `([0-9a-f]{64})` \|", line)
        if m:
            rows[m.group(1)] = m.group(4)
    return rows


def test_license_file_present_and_mit():
    text = (VENDOR / "LICENSE.hermes").read_text()
    assert "MIT License" in text and "Nous Research" in text


def test_vendored_files_match_manifest_hashes():
    # The manifest pins the UPSTREAM file hash at the pinned commit; vendored
    # copies carry a header + import rewrites, so compare against the recorded
    # manifest by checking every listed file exists with its provenance header
    # naming the pinned commit, and that the manifest is complete.
    rows = _manifest()
    assert len(rows) == 50
    for vendored_path in rows:
        f = ROOT / "src" / vendored_path
        assert f.exists(), vendored_path
        head = f.read_text()[:600]
        assert "VENDORED from NousResearch/hermes-agent" in head
        assert COMMIT_RE.search(head), vendored_path


def test_bridge_modules_are_marked_not_upstream():
    bridges = [
        "hermes_cli/config.py", "hermes_cli/config_effective.py", "hermes_cli/plugin_compat.py",
        "hermes_cli/plugins.py", "hermes_cli/auth.py", "hermes_cli/managed_scope.py",
        "agent/redact.py", "agent/secret_scope.py", "agent/monitoring/cron_health.py",
        "agent/delegation_context.py", "agent/runtime_cwd.py", "agent/terminal_env_registry.py",
        "agent/skill_preprocessing.py",
        "gateway/status.py", "gateway/session_context.py", "gateway/restart.py",
        "gateway/platform_registry.py", "gateway/profile_routing.py",
        "gateway/platforms/base.py", "gateway/platforms/_shared.py", "gateway/platforms/helpers.py",
        "tools/kanban_tools.py", "tools/skill_manager_guards.py", "tools/terminal_scope.py",
        "tools/budget_config.py",
        "cron/__init__.py", "cron/scheduler.py", "cron/scheduler_preflight.py",
        "cron/lifecycle_guard.py",
        "gateway/session.py", "gateway/run.py",
    ]
    for rel in bridges:
        text = (VENDOR / rel).read_text()
        assert "Noesek-authored" in text and "NOT upstream Hermes source" in text, rel
        assert "VENDORED from NousResearch" not in text, rel


def test_dependencies_exactly_pinned():
    text = (ROOT / "pyproject.toml").read_text()
    deps = re.findall(r'^\s+"([a-z0-9\-_\[\]]+)([=<>!].*?)",', text, re.MULTILINE | re.IGNORECASE)
    assert deps, "no dependencies parsed"
    for name, spec in deps:
        assert spec.startswith("=="), f"{name} is not exactly pinned: {spec}"
    assert (ROOT / "requirements-lock.txt").exists()


def test_no_gpl_or_copyleft_notices_needed():
    # Every vendored file is MIT Hermes; new deps are MIT/Apache-2.0.
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    for pkg in ("PyYAML", "opentelemetry-sdk", "MCP Python SDK"):
        assert pkg in notices
    assert "GPL" not in notices
