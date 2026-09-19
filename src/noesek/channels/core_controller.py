"""Shared controller instance for channel routers."""
from ..core.controller import Controller

_controller = None


def get_controller() -> Controller:
    global _controller
    if _controller is None:
        _controller = Controller()
    return _controller
