# VENDORED from NousResearch/hermes-agent @ c712f06dcdd24053a4118f38d2090ac53137ecfc
# Upstream path: tools/__init__.py
# License: MIT (c) 2025 Nous Research - see noesek/vendor/hermes/LICENSE.hermes
# Local changes: import-path rewrites into the noesek.vendor.hermes namespace only;
# no semantic modifications. Do not edit by hand; regenerate via scripts/vendor_hermes.py.

"""Tools package namespace. Kept side-effect free: importing ``tools`` must not
load the tool stack (some subsystems import it while ``hermes_cli.config`` is
still initializing). Import concrete submodules directly."""


def check_file_requirements():
    """File tools only require terminal backend availability."""
    from .terminal_tool import check_terminal_requirements
    return check_terminal_requirements()


__all__ = ["check_file_requirements"]
