"""Noesek-authored bridge (NOT upstream Hermes source)."""
import contextlib


@contextlib.contextmanager
def managed_scope(*a, **kw):
    yield
