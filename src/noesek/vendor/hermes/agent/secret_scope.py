"""Noesek-authored bridge (NOT upstream Hermes source).

Noesek has no Hermes secret-multiplexing subsystem, so multiplexing is always
inactive and there is no installed scope. ``load_env_file`` is a plain
KEY=VALUE .env reader matching upstream's contract for the vendored
cron/env_settings module.
"""
from pathlib import Path


def is_multiplex_active() -> bool:
    return False


def current_secret_scope():
    return None


def load_env_file(path) -> dict:
    out = {}
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


class UnscopedSecretError(RuntimeError):
    pass


def get_secret(name: str):
    raise UnscopedSecretError(name)


def serves_routed_profile() -> bool:
    return False
