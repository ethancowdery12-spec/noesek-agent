"""Noesek-authored bridge (NOT upstream Hermes source).

Upstream gateway/run.py is the full GatewayRunner daemon, which is not vendored:
Noesek's controller and channel layer own orchestration. This bridge provides the
two symbols lazily imported by vendored modules (a logger keeping upstream's
logger name for observability, and the in-process runner reference, always None
because no Hermes GatewayRunner runs inside Noesek).
"""
import logging

logger = logging.getLogger("gateway.run")

_gateway_runner_ref = None
