"""Noesek-authored bridge (NOT upstream Hermes source).

Upstream's platform registry maps gateway platforms (discord, slack, ...) to
adapter modules. Noesek's channel layer owns platforms; the registry is empty.
"""


class _EmptyRegistry:
    def get(self, *a, **kw):
        return None

    def __iter__(self):
        return iter(())

    def __contains__(self, item):
        return False


platform_registry = _EmptyRegistry()
