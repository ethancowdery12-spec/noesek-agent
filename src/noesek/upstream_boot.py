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
colors:
  banner_border: "#0E7490"
  banner_title: "#22D3EE"
  banner_accent: "#34D399"
  banner_dim: "#155E75"
  banner_text: "#E6EDF3"
  ui_accent: "#34D399"
  ui_label: "#22D3EE"
  session_border: "#155E75"
banner_logo: |
  [bold #22D3EE] _  _  ___  ___  ___  _  __
  | \\| |/ _ \\/ __|/ __|| |/ /
  | .` | (_) \\__ \\| _| |   <
  |_|\\_|\\___/|___/|___||_|\\_\\
  [/]
banner_hero: |
  [bold #34D399]███╗   ██╗[/]
  [bold #34D399]████╗  ██║[/]
  [bold #34D399]██╔██╗ ██║[/]
  [bold #34D399]██║╚██╗██║[/]
  [bold #34D399]██║ ╚████║[/]
  [bold #34D399]╚═╝  ╚═══╝[/]
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
    _persist_default_skin(home)
    return home


def _persist_default_skin(home: Path) -> None:
    """Record display.skin=noesek in the vendored CLI config.

    Upstream startup re-reads its own config and activates whatever
    ``display.skin`` says (default: "default"), which would otherwise undo
    the boot shim's set_active_skin call. A user-chosen skin is respected:
    only an absent or "default" value is rewritten.
    """
    import yaml
    cfg = home / "config.yaml"
    data = {}
    if cfg.exists():
        try:
            data = yaml.safe_load(cfg.read_text()) or {}
        except Exception:
            return  # unparseable user config: leave it untouched
        if not isinstance(data, dict):
            return
    display = data.get("display")
    if isinstance(display, dict):
        current = display.get("skin")
        if current not in (None, "", "default"):
            return
    else:
        data["display"] = {}
    data["display"]["skin"] = SKIN_NAME
    cfg.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


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


def _patch_banner_label() -> None:
    """Point the canonical banner/version label at the Noesek product version."""
    from . import __version__
    from hermes_cli import banner as _banner
    _banner.format_banner_version_label = lambda: f"Noesek Agent v{__version__}"


_SUBCOMMAND_NAMES = None


def _command_names() -> tuple:
    """User-visible subcommand words from the shipped CLI manifest."""
    global _SUBCOMMAND_NAMES
    if _SUBCOMMAND_NAMES is None:
        import json
        manifest = Path(__file__).parent / "data" / "cli-manifest.json"
        names = {c["path"][0] for c in json.loads(manifest.read_text())["commands"] if c.get("path")}
        names |= {"chat", "setup", "model", "config"}
        _SUBCOMMAND_NAMES = tuple(sorted(names, key=len, reverse=True))
    return _SUBCOMMAND_NAMES


_COMMAND_RE = None
_PRODUCT_RE = None
_BARE_RE = None
_HOME_RE = None
_STANDALONE_RE = None


def _regexes():
    """Compile the output-branding patterns once.

    ``hermes`` is rewritten only where a user would read it as the command to
    type: followed by a subcommand or flag (``hermes model``, ``hermes
    --version``), or standing alone inside quotes/backticks (``run `hermes` ``).
    Capitalised ``Hermes`` on its own is always the product name in this CLI's
    user-facing copy (``Hermes Setup``, ``Configure Hermes``) and is rewritten.
    Module names (hermes_cli), repo slugs (NousResearch/hermes-agent), file
    and env vars (HERMES_HOME, uppercase) never match. The vendored runtime's
    home IS the Noesek home, so literal ``.hermes`` path mentions are rewritten
    to ``.noesek`` - that is where the files actually live.
    """
    global _COMMAND_RE, _PRODUCT_RE, _BARE_RE, _HOME_RE, _STANDALONE_RE
    import re
    if _COMMAND_RE is None:
        subs = "|".join(re.escape(n) for n in _command_names())
        _COMMAND_RE = re.compile(r"(?<![\w/.:\-])hermes(?=\s+(?:--?[a-zA-Z][\w-]*|" + subs + r")(?![\w-]))")
        _PRODUCT_RE = re.compile(r"\bHermes Agent\b")
        _BARE_RE = re.compile(r"\bHermes\b")
        _HOME_RE = re.compile(r"\.hermes(?![\w-])")
        _STANDALONE_RE = re.compile(r"(?<![\w/.:\-])hermes(?=[`'\"])")
    return _COMMAND_RE, _PRODUCT_RE, _BARE_RE, _HOME_RE, _STANDALONE_RE


class _BrandingStream:
    """Transparent write-through wrapper applying Noesek output branding.

    Renderers (rich, prompt_toolkit) split styled lines into segments, so a
    token can straddle two write() calls ("~/." then "hermes/skills/"). The
    last _HOLD chars of each chunk are held back and prepended to the next;
    flush() always drains them, so prompts and final output are never lost.
    """

    _HOLD = 32  # longest pattern span: quote + "hermes" + longest subcommand

    def __init__(self, inner):
        self._inner = inner
        self._pending = ""

    def _rewrite(self, text):
        if "hermes" not in text and "Hermes" not in text:
            return text
        cmd, product, bare, home, standalone = _regexes()
        text = cmd.sub("noesek", text)
        text = product.sub("Noesek Agent", text)
        text = bare.sub("Noesek Agent", text)
        text = home.sub(".noesek", text)
        text = standalone.sub("noesek", text)
        return text

    def write(self, text):
        if not isinstance(text, str):
            return self._inner.write(text)
        # Rewrite the combined text FIRST so a renderer split can never fall
        # inside a pattern, then hold back a tail so a token still incomplete
        # at the chunk end can be finished by the next write.
        text = self._rewrite(self._pending + text)
        if len(text) <= self._HOLD:
            self._pending = text
            return 0
        head, self._pending = text[:-self._HOLD], text[-self._HOLD:]
        return self._inner.write(head)

    def flush(self):
        if self._pending:
            pending, self._pending = self._pending, ""
            self._inner.write(self._rewrite(pending))
        return self._inner.flush()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _install_output_branding() -> None:
    """Rewrite residual upstream command/product mentions on the terminal.

    Terminal surfaces only: the ACP stdio server (noesek-acp) must never be
    wrapped - protocol frames could legitimately contain these strings.
    """
    if not isinstance(sys.stdout, _BrandingStream):
        sys.stdout = _BrandingStream(sys.stdout)
    if not isinstance(sys.stderr, _BrandingStream):
        sys.stderr = _BrandingStream(sys.stderr)


def main() -> int:
    """Entry: boot the full vendored CLI with Noesek branding."""
    boot_env()
    _patch_prog()
    _patch_banner_label()
    _activate_skin()
    _install_output_branding()
    from .core.upstream_safety import install as _install_safety
    _install_safety()
    from hermes_cli.main import main as upstream_main
    result = upstream_main()
    return int(result) if isinstance(result, int) else 0


def main_run_agent() -> int:
    """noesek-agent entry: upstream agent runner with the Noesek home mapped."""
    boot_env()
    _patch_banner_label()
    _install_output_branding()
    from run_agent import main as run_agent_main
    result = run_agent_main()
    return int(result) if isinstance(result, int) else 0


def main_acp() -> int:
    """noesek-acp entry: upstream ACP adapter with the Noesek home mapped."""
    boot_env()
    _patch_acp_identity()
    from acp_adapter.entry import main as acp_main
    result = acp_main()
    return int(result) if isinstance(result, int) else 0


def _patch_acp_identity() -> None:
    """Rebrand the vendored ACP adapter's protocol metadata.

    The wire itself is untouched; only the agent identity and auth-method
    copy an ACP client displays change (agentInfo name/version, auth method
    names/descriptions, setup terminal args).
    """
    from . import __version__
    import acp_adapter.server as _server
    import acp_adapter.auth as _auth

    _original_initialize = _server.HermesACPAgent.initialize

    async def _initialize(self, protocol_version, client_capabilities=None,
                          client_info=None, **kwargs):
        response = await _original_initialize(
            self, protocol_version, client_capabilities=client_capabilities,
            client_info=client_info, **kwargs)
        if getattr(response, "agent_info", None) is not None:
            response.agent_info.name = "noesek-agent"
            response.agent_info.version = __version__
        return response

    _server.HermesACPAgent.initialize = _initialize

    _original_build = _auth.build_auth_methods

    def _build_auth_methods():
        methods = _original_build()
        for m in methods:
            for field in ("name", "description"):
                value = getattr(m, field, None)
                if isinstance(value, str) and "Hermes" in value:
                    setattr(m, field, value.replace("Hermes'", "Noesek Agent's")
                            .replace("Hermes", "Noesek Agent"))
            if getattr(m, "id", None) == _auth.TERMINAL_SETUP_AUTH_METHOD_ID:
                m.id = "noesek-setup"
        return methods

    _auth.build_auth_methods = _build_auth_methods
    _server.build_auth_methods = _build_auth_methods


def run_vendored(argv) -> int:
    """Run one vendored upstream command (``noesek setup``, ``noesek model``).

    Same Noesek layer as the interactive boot: Noesek home, noesek skin,
    branded parser/output, and the safety shim. argv excludes the executable
    name (e.g. ["setup", "--non-interactive"]).
    """
    boot_env()
    _patch_prog()
    _patch_banner_label()
    _activate_skin()
    _install_output_branding()
    from .core.upstream_safety import install as _install_safety
    _install_safety()
    from hermes_cli.main import main as upstream_main
    old_argv = sys.argv
    sys.argv = ["noesek"] + [str(a) for a in argv]
    try:
        result = upstream_main()
        return int(result) if isinstance(result, int) else 0
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    sys.exit(main())
