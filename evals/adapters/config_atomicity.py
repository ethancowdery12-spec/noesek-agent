"""Adapter for upstream evals/cli_fallback_add_picker_error.py (Hermes c712f06d).

Upstream intent: a command that fails mid-way must leave prior config
byte-identical and exit with a plain error, not a crash. Noesek target: the
`noesek config` read surface plus failing lookups against an isolated home -
the invariant is that CLI operations never mutate or corrupt config state.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, out_dir, run_cli


def tree_hash(home: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(home.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(home)).encode()); h.update(f.read_bytes())
    return h.hexdigest()


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    (home / "config.yaml").write_text("gateway:\n  channels:\n    - telegram\n")
    before = tree_hash(home)
    checks = {}
    r = run_cli(home, "--json", "config")
    checks["snapshot_ok"] = r.returncode == 0 and json.loads(r.stdout) is not None
    r = run_cli(home, "config", "no_such_key")
    checks["missing_key_exit"] = r.returncode
    checks["missing_key_clean"] = r.returncode != 0 and "Traceback" not in r.stderr
    checks["missing_key_message"] = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""
    # doctor's job is to REPORT problems, so a nonzero exit is fine; the
    # invariant is a clean run: valid JSON on stdout, no traceback.
    r = run_cli(home, "--json", "doctor")
    try:
        checks["doctor_ok"] = json.loads(r.stdout) is not None and "Traceback" not in r.stderr
    except json.JSONDecodeError:
        checks["doctor_ok"] = False
    checks["tree_unchanged"] = tree_hash(home) == before
    ok = all([checks["snapshot_ok"], checks["missing_key_clean"],
              checks["doctor_ok"], checks["tree_unchanged"]])
    emit("pass" if ok else "fail", **checks)


if __name__ == "__main__":
    main()
