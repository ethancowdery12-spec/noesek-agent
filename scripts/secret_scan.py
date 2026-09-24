#!/usr/bin/env python3
"""Secret-scan gate (skills batch 1, item 4).

Scans every git-tracked file with detect-secrets (Apache-2.0, Yelp; pinned
in the test extra) and fails on findings that are NOT in .secrets.baseline.
The baseline records pre-existing, human-reviewed false positives (release
SHA256s, upstream commit hashes, fake adapter/webhook test secrets,
throwaway CI service credentials, placeholder example URLs). Review the
baseline diff when it changes; never baseline a real credential.

Suppression of a deliberate test sentinel on ONE line: add
`# pragma: allowlist secret` to that line (detect-secrets honors it).

Exclusions (never scanned):
- vendor/, tests/upstream/ - byte-identical upstream trees; not ours to change
- generated manifest/result JSON with content hashes (not credentials)
- lock files, the baseline itself

Usage:
  python scripts/secret_scan.py                 gate: fail on new findings (CI)
  python scripts/secret_scan.py --write-baseline  regenerate .secrets.baseline after review
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASELINE = Path(".secrets.baseline")

SKIP_PREFIXES = ("vendor/", "tests/upstream/")
SKIP_FILES = {
    "uv.lock",
    "requirements-lock.txt",
    ".secrets.baseline",
    "scripts/secret_scan.py",
    # generated data: content hashes and upstream-derived digests, not credentials
    "compat/cli-manifest.json",
    "src/noesek/data/cli-manifest.json",
    "evals/compat-manifest.json",
    "evals/adapter-results.json",
}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines()
            if f and not f.startswith(SKIP_PREFIXES) and f not in SKIP_FILES]


def scan(files):
    from detect_secrets.core.secrets_collection import SecretsCollection
    from detect_secrets.settings import default_settings
    secrets = SecretsCollection()
    with default_settings():
        for f in files:
            try:
                secrets.scan_file(f)
            except (UnicodeDecodeError, OSError):
                continue  # binary or unreadable - not scannable text
    return secrets


def _count(secrets) -> int:
    return sum(len(v) for v in secrets.data.values())


def main() -> int:
    try:
        from detect_secrets.core import baseline as ds_baseline
        import detect_secrets  # noqa: F401
    except ImportError:
        print("detect-secrets is not installed: pip install -e '.[test]'", file=sys.stderr)
        return 2

    files = tracked_files()
    secrets = scan(files)

    if "--write-baseline" in sys.argv:
        import importlib.metadata
        data = {"version": importlib.metadata.version("detect-secrets"),
                "generated_by": "scripts/secret_scan.py --write-baseline (reviewed false positives only)",
                "results": secrets.json()}
        BASELINE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(f"baseline written: {_count(secrets)} reviewed finding(s) across {len(files)} tracked files")
        return 0

    if not BASELINE.is_file():
        print("no .secrets.baseline - generate one after review: python scripts/secret_scan.py --write-baseline",
              file=sys.stderr)
        return 2

    old = ds_baseline.load(json.loads(BASELINE.read_text()), str(BASELINE))
    new = secrets - old
    n = _count(new)
    if n:
        print(f"SECRET SCAN FAILED: {n} NEW finding(s) not in .secrets.baseline:")
        for filename, found in new.data.items():
            for sec in found:
                print(f"  {filename}:{sec.line_number}  ({sec.type})")
        print("Fix: remove the secret (rotate it if it was ever real), or mark a deliberate "
              "test sentinel with '# pragma: allowlist secret'. Baseline changes need review.")
        return 1
    print(f"secret scan clean: {len(files)} tracked files, no new findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
