"""Adapter for upstream evals/goal_command_parity.py (Hermes c712f06d).

Upstream intent: semantic parity oracle - the same command sequence in fresh
processes with distinct homes must yield identical state and queued output.
Narrowed scope: Noesek has no /goal command, so this adapter applies the
oracle to the Noesek pairing command surface (state + list output parity).
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, env_for, out_dir, run_cli

GEN = ("from noesek.channels.authorization import NoesekAuthorizationGate;"
       "g = NoesekAuthorizationGate();"
       "print(g.pairing_store.generate_code('slack', 'u-parity', 'Parity User') or '')")


def sequence(home: Path):
    code = subprocess.run([sys.executable, "-c", GEN], env=env_for(home),
                          capture_output=True, text=True, timeout=30).stdout.strip()
    approve = run_cli(home, "--json", "pairing", "approve", "slack", code)
    listed = run_cli(home, "--json", "pairing", "list")
    pending = run_cli(home, "--json", "pairing", "pending")
    return {"approve": json.loads(approve.stdout), "list": json.loads(listed.stdout),
            "pending": json.loads(pending.stdout)}


VOLATILE = {"approved_at"}


def strip_volatile(node):
    if isinstance(node, dict):
        return {k: strip_volatile(v) for k, v in node.items() if k not in VOLATILE}
    if isinstance(node, list):
        return [strip_volatile(v) for v in node]
    return node


def main():
    out = out_dir()
    results = []
    for label in ("home-a", "home-b"):
        home = out / label; home.mkdir()
        results.append(sequence(home))
    state_a, state_b = strip_volatile(results[0]), strip_volatile(results[1])
    ok = state_a == state_b
    (out / "parity.json").write_text(json.dumps({"a": results[0], "b": results[1]}, indent=2))
    emit("pass" if ok else "fail", state_identical=ok,
         presentation_differences="approved_at timestamps differ (expected)",
         deviation="pairing command surface (Noesek has no /goal command)")


if __name__ == "__main__":
    main()
