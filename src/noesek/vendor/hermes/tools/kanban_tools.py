"""Noesek-authored bridge (NOT upstream Hermes source). Noesek has no kanban toolset."""


def _profile_has_kanban_toolset(*a, **kw) -> bool:
    return False
