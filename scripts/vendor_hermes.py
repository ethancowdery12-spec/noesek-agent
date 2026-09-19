"""Vendor selected Hermes Agent (NousResearch/hermes-agent, MIT) modules into Noesek.

Copies upstream files verbatim except for mechanical import-path rewrites into the
noesek.vendor.hermes namespace, prepends a provenance header, and records per-file
SHA-256 in VENDORING.md's manifest (generated separately).
"""
from pathlib import Path
import hashlib, json, sys

SRC = Path("/home/sandbox/work/hermes-src")
DST = Path("/home/sandbox/work/noesek-agent/src/noesek/vendor/hermes")
COMMIT = "c712f06dcdd24053a4118f38d2090ac53137ecfc"

FILES = [
    "utils.py",
    "hermes_constants.py",
    "hermes_time.py",
    "tools/__init__.py",
    "tools/interrupt.py",
    "tools/approval.py",
    "tools/approval_context.py",
    "tools/approval_detection.py",
    "tools/approval_floors.py",
    "tools/approval_gateway_wait.py",
    "tools/approval_human_wait.py",
    "tools/approval_prompt.py",
    "tools/approval_smart.py",
    "cron/occurrences.py",
    "cron/executions.py",
    "cron/incidents.py",
    "cron/delivery_queue.py",
    "tools/ansi_strip.py",
    "agent/retry_utils.py",
    "hermes_cli/sqlite_util.py",
    "hermes_cli/sqlite_runtime.py",
    "hermes_state_wal.py",
    "cron/jobs.py",
    "cron/env_settings.py",
    "cron/notepad.py",
    "cron/unreachable_retry.py",
    "agent/skill_utils.py",
    "tools/path_security.py",
    "tools/skills_tool.py",
    "tools/skills_tool_dedup.py",
    "tools/skills_tool_plugin.py",
    "tools/skills_tool_setup.py",
    "tools/skill_ledger.py",
    "tools/skill_provenance.py",
    "tools/skill_usage.py",
    "tools/skills_guard.py",
    "tools/skill_linter.py",
    "tools/registry.py",
    "gateway/config.py",
    "gateway/config_loader.py",
    "gateway/channel_directory.py",
    "gateway/shutdown_watchdog.py",
    "plugins/__init__.py",
    "plugins/plugin_loader.py",
    "plugins/plugin_storage.py",
    "plugins/plugin_utils.py",
    "gateway/whatsapp_identity.py",
    "gateway/bot_loop_guard.py",
    "gateway/pairing.py",
    "gateway/authz_mixin.py",
]

NS = "noesek.vendor.hermes"

# Ordered (old, new) literal rewrites. Longest/most-specific first where prefixes overlap.
REWRITES = [
    # Generic prefix rules: every upstream intra-package import moves into the
    # vendor namespace. Modules not vendored resolve to Noesek-authored bridges
    # of the same name, or fail loudly if no bridge exists.
    ("from hermes_cli.", f"from {NS}.hermes_cli."),
    ("from hermes_constants import ", f"from {NS}.hermes_constants import "),
    ("from hermes_time import ", f"from {NS}.hermes_time import "),
    ("from hermes_state_wal import ", f"from {NS}.hermes_state_wal import "),
    ("from cron.", f"from {NS}.cron."),
    ("from cron import ", f"from {NS}.cron import "),
    ("from agent.", f"from {NS}.agent."),
    ("from agent import ", f"from {NS}.agent import "),
    ("from gateway.", f"from {NS}.gateway."),
    ("from tools.", f"from {NS}.tools."),
    ("from tools import ", f"from {NS}.tools import "),
    ("from utils import ", f"from {NS}.utils import "),
    # Lazy import_module string targets inside tools/approval.py's plugin-compat map.
    ("('tools.", f"('{NS}.tools."),
    ("('hermes_cli.", f"('{NS}.hermes_cli."),
]

HEADER = '''# VENDORED from NousResearch/hermes-agent @ {commit}
# Upstream path: {path}
# License: MIT (c) 2025 Nous Research - see noesek/vendor/hermes/LICENSE.hermes
# Local changes: import-path rewrites into the noesek.vendor.hermes namespace only;
# no semantic modifications. Do not edit by hand; regenerate via scripts/vendor_hermes.py.

'''

manifest = {}
for rel in FILES:
    src = SRC / rel
    text = src.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    out = text
    for old, new in REWRITES:
        out = out.replace(old, new)
    dst = DST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(HEADER.format(commit=COMMIT, path=rel) + out, encoding="utf-8")
    manifest[rel] = sha
    print(f"vendored {rel} ({len(text.splitlines())} lines, sha256 {sha[:12]}...)")

# Vendored cron/__init__.py is Noesek-authored: upstream's pulls in jobs/scheduler, not vendored.
(DST / "cron" / "__init__.py").write_text(
    '"""Vendored Hermes cron persistence core: occurrences, executions, incidents, delivery queue.\n'
    '\n'
    'Noesek-authored package init (NOT upstream Hermes source): upstream\n'
    'cron/__init__.py imports the full scheduler stack, which is not vendored.\n'
    'Import concrete submodules directly.\n'
    '"""\n', encoding="utf-8")

(DST / "tools" / "__init__.py")  # already vendored above
print(json.dumps(manifest, indent=1))
