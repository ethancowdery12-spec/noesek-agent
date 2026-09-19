"""Noesek-authored bridge (NOT upstream Hermes source).

Upstream's lifecycle guard detects Hermes-gateway start/stop/restart commands
so cron jobs cannot respawn the gateway daemon. Noesek runs no Hermes gateway
daemon, so no command can lifecycle-manage it; both entry points are inert.
"""


class GatewayLifecycleBlocked(ValueError):
    """Upstream-compatible exception type (cron/jobs.py lets ValueError propagate)."""


def contains_gateway_lifecycle_command(command: str) -> bool:
    return False


def check_gateway_lifecycle(prompt, script=None) -> None:
    return None
