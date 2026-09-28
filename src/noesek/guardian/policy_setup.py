"""Owner questionnaire: the only sanctioned writer for the guardian policy
file. Runs interactively (noesek guardian-setup), collects the owner's band
choices, and writes the HMAC-signed policy via guardian/policy.write_policy."""
from __future__ import annotations

import asyncio

from ..config import settings
from . import policy


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        ans = ""
    return ans or default


def _ask_band(prompt: str, default: str = "escalate") -> str:
    while True:
        ans = _ask(f"{prompt} (allow/escalate/deny)", default).lower()
        if ans in policy.BANDS:
            return ans
        print("  please answer allow, escalate, or deny")


def _ask_list(prompt: str) -> list[str]:
    raw = _ask(f"{prompt} (comma-separated, or blank for none)")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _live_registry_snapshot() -> list[str]:
    """Best-effort snapshot of the trained tool registry for the new-tool
    default. Empty when the registry can't be enumerated (new_tool_default
    then stays inactive rather than misfiring on known tools)."""
    try:
        import os
        os.environ.setdefault("NOESEK_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        from finetune.dump_tools import production_specs  # type: ignore

        return sorted(s.get("name", "") for s in production_specs() if s.get("name"))
    except Exception:  # noqa: BLE001
        return []


def run_questionnaire() -> int:
    print("Guardian policy setup - your answers write one integrity-protected file,")
    print(f"  {policy._policy_path()}")
    print("Hand edits invalidate it; re-run this setup to change anything.")
    print("The injection floor (credential access, exfiltration, remote exec) always")
    print("denies at threshold and cannot be overridden by anything you choose here.")
    print()

    rules: list[dict] = []
    connectors = _ask_list("Which connectors do you use (e.g. gmail, calendar, strava)")
    for conn in connectors:
        band = _ask_band(f"Minimum band for NEW/untrained {conn} tools (prefix '{conn}.')", "escalate")
        rules.append({"match": "prefix", "pattern": f"{conn}.", "kind": "floor", "band": band,
                      "note": f"connector floor from setup ({conn})"})

    for tool in _ask_list("Tools the guardian should ALWAYS allow"):
        rules.append({"match": "tool", "pattern": tool, "kind": "pin", "band": "allow",
                      "note": "owner always-allow"})
    for tool in _ask_list("Tools the guardian should ALWAYS deny"):
        rules.append({"match": "tool", "pattern": tool, "kind": "pin", "band": "deny",
                      "note": "owner always-deny"})

    money_rules = [r for r in rules if r["band"] == "allow" and any(
        k in r["pattern"].lower() for k in ("pay", "money", "charge", "purchase", "bank"))]
    if money_rules:
        print()
        print("WARNING: you pinned payment/money tools to ALLOW. The guardian will not")
        print("stop those calls. The approval flow may still ask before executing them.")
        if _ask("Type YES to confirm allow-pinned money tools") != "YES":
            print("setup cancelled; no file written.")
            return 1

    print()
    print("Summary:")
    if not rules:
        print("  (no overrides - the model verdict stands everywhere; untrained tools")
        print("   still fall back to the new-tool default once registered)")
    for r in rules:
        print(f"  {r['match']}:{r['pattern']}  {r['kind']} -> {r['band']}   # {r['note']}")
    if _ask("Write this policy?", "y").lower() not in ("y", "yes"):
        print("setup cancelled; no file written.")
        return 1

    known = _live_registry_snapshot()
    if settings.guardian_policy_key.strip():
        dest = asyncio.run(policy.awrite_policy(rules, answers_summary=f"connectors={connectors}",
                                                known_tools=known))
    else:
        dest = policy.write_policy(rules, answers_summary=f"connectors={connectors}", known_tools=known)
    print(f"wrote {dest} (integrity-protected; {len(rules)} rules, {len(known)} known tools snapshotted)")
    return 0
