"""Noesek-authored bridge (NOT upstream Hermes source).

Upstream scopes session env values through the gateway's contextvars. Noesek
approvals run inside its own controller, so this falls back to process env.
"""
import os


def get_session_env(name: str, default: str = "") -> str:
    return os.getenv(name, default)
