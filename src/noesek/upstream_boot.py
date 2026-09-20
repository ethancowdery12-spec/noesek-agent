"""Noesek boot shim for the vendored upstream CLI (v3 full fork).

Launches the complete upstream hermes_cli experience with Noesek branding
applied from OUR layer - the vendored tree stays byte-identical:

- HERMES_HOME maps to NOESEK_HOME (default ~/.noesek) so state, config,
  sessions, and skins live in the Noesek home.
- A ``noesek`` skin (wordmark, agent name, welcome/goodbye, prompt symbol)
  is installed into <home>/skins/noesek.yaml and activated via the upstream
  skin engine - the supported branding hook, no vendored edits.
- The top-level argparse parser's user-visible prog/description are wrapped
  to read ``noesek`` (internal Python identifiers stay upstream-named, which
  preserves upstream diff/sync and the MIT provenance manifest).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SKIN_NAME = "noesek"

_SKIN_YAML = """\
name: noesek
description: Noesek Agent default skin (installed by the noesek boot shim).
branding:
  agent_name: "Noesek Agent"
  welcome: "Welcome to Noesek Agent! Type your message or /help for commands."
  goodbye: "Goodbye!"
  response_label: " > Noesek "
  prompt_symbol: ">"
  help_header: "Available Commands"
banner_logo: |
  [bold] _  _  ___  ___  ___  _  __
  | \\| |/ _ \\/ __|/ __|| |/ /
  | .` | (_) \\__ \\| _| |   <
  |_|\\_|\\___/|___/|___||_|\\_\\[/bold]
"""


def noesek_home() -> Path:
    return Path(os.environ.get("NOESEK_HOME", "~/.noesek")).expanduser()


def boot_env() -> Path:
    """Map the Noesek home onto the vendored runtime and install the skin."""
    home = noesek_home()
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HERMES_HOME"] = str(home)
    skins = home / "skins"
    skins.mkdir(parents=True, exist_ok=True)
    target = skins / f"{SKIN_NAME}.yaml"
    # Refresh only our own managed file; never touch user-authored skins.
    if not target.exists() or target.read_text() != _SKIN_YAML:
        target.write_text(_SKIN_YAML)
    return home


def _patch_prog() -> None:
    """Wrap the vendored top-level parser so --help and errors read ``noesek``."""
    import hermes_cli._parser as hp

    original = hp.build_top_level_parser

    def wrapped():
        parser, subparsers, chat_parser = original()
        parser.prog = "noesek"
        parser.description = "Noesek Agent - AI assistant with tool-calling capabilities"
        chat_parser.prog = "noesek chat"
        return parser, subparsers, chat_parser

    hp.build_top_level_parser = wrapped


def _activate_skin() -> None:
    from hermes_cli.skin_engine import set_active_skin
    set_active_skin(SKIN_NAME)


def main() -> int:
    """Entry: boot the full vendored CLI with Noesek branding."""
    boot_env()
    _patch_prog()
    _activate_skin()
    from .core.upstream_safety import install as _install_safety
    _install_safety()
    from hermes_cli.main import main as upstream_main
    result = upstream_main()
    return int(result) if isinstance(result, int) else 0


def main_run_agent() -> int:
    """noesek-agent entry: upstream agent runner with the Noesek home mapped."""
    boot_env()
    from run_agent import main as run_agent_main
    result = run_agent_main()
    return int(result) if isinstance(result, int) else 0


def main_acp() -> int:
    """noesek-acp entry: upstream ACP adapter with the Noesek home mapped."""
    boot_env()
    from acp_adapter.entry import main as acp_main
    result = acp_main()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
