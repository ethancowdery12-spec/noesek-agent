"""Adapter for upstream evals/auth_pool_controls.py (Hermes c712f06d).

Upstream intent: exercise the production auth lifecycle (parser, command,
persistence) in isolated homes, loopback-only, no real credentials. Noesek
target: the pairing lifecycle through the vendored Hermes PairingStore and the
`noesek pairing` CLI in an isolated NOESEK_HOME.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, env_for, out_dir, run_cli


def gen_code(home):
    helper = (
        "from noesek.channels.authorization import NoesekAuthorizationGate;"
        "g = NoesekAuthorizationGate();"
        "print(g.pairing_store.generate_code('telegram', 'user-1', 'User One') or '')")
    r = subprocess.run([sys.executable, "-c", helper], env=env_for(home),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def main():
    out = out_dir(); home = out / "home"; home.mkdir()
    steps = {}
    r = run_cli(home, "--json", "pairing", "pending")
    steps["pending_initial"] = json.loads(r.stdout) if r.returncode == 0 else r.stderr
    code = gen_code(home)
    steps["code_generated"] = bool(code)
    r = run_cli(home, "--json", "pairing", "pending")
    pend = json.loads(r.stdout); steps["pending_after_generate"] = len(pend)
    r = run_cli(home, "--json", "pairing", "approve", "telegram", code)
    steps["approve"] = json.loads(r.stdout) if r.returncode == 0 else r.stderr
    r = run_cli(home, "--json", "pairing", "list")
    approved = json.loads(r.stdout); steps["approved_listed"] = any(
        "user-1" in json.dumps(row) for row in approved)
    # restart persistence: a fresh CLI process must see the approval
    r2 = run_cli(home, "--json", "pairing", "list")
    steps["survives_fresh_process"] = json.loads(r2.stdout) == approved
    r = run_cli(home, "--json", "pairing", "revoke", "telegram", "user-1")
    steps["revoke"] = json.loads(r.stdout) if r.returncode == 0 else r.stderr
    r = run_cli(home, "--json", "pairing", "list")
    steps["list_after_revoke"] = json.loads(r.stdout)
    ok = (steps["code_generated"] and steps["pending_after_generate"] >= 1
          and steps["approved_listed"] and steps["survives_fresh_process"]
          and steps["list_after_revoke"] == [])
    emit("pass" if ok else "fail", **steps)


if __name__ == "__main__":
    main()
