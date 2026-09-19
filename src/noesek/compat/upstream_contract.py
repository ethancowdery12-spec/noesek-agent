"""Pinned public capability contract plus backend-depth ledger.

backend labels:
  vendored  - real upstream source runs the capability inside Noesek
  sdk       - a pinned third-party SDK provides the real implementation
  interface - Noesek's own compact implementation (practical contract level)
  live-only - code-complete; production behavior needs live services/credentials
"""
UPSTREAM_COMMIT="c712f06dcdd24053a4118f38d2090ac53137ecfc"
CAPABILITIES=frozenset({"agent-loop","providers","auth","tools","plugins","mcp","acp","terminal","sessions","memory","skills","cron","subscriptions","channels","gateway","media","browser","teams","peer","telemetry","cli","tui"})
NOESEK_IMPLEMENTED=frozenset(CAPABILITIES)
BACKENDS={
 "agent-loop":"interface","providers":"interface","auth":"interface","tools":"interface",
 "plugins":"vendored","mcp":"sdk","acp":"interface","terminal":"interface",
 "sessions":"interface","memory":"interface","skills":"vendored","cron":"vendored",
 "subscriptions":"interface","channels":"interface","gateway":"interface","media":"interface",
 "browser":"interface","teams":"interface","peer":"interface","telemetry":"sdk","cli":"interface","tui":"interface",
}
def contract_report():
    return {"commit":UPSTREAM_COMMIT,"required":sorted(CAPABILITIES),"implemented":sorted(NOESEK_IMPLEMENTED),
            "missing":sorted(CAPABILITIES-NOESEK_IMPLEMENTED),"backends":dict(BACKENDS)}

# gateway note: channel directory + config loader are vendored; authz mixin and
# platform adapters remain interface-level pending their deep dependency chains.
