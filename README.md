# Noesek Agent

Self-hostable WhatsApp-first hybrid AI agent runtime with a Hermes-compatible CLI.

## Install

The release installer verifies a pinned SHA-256 before installing into `pipx` or an isolated managed virtual environment. It does not need root and exposes both `noesek` and `hermes`.

Use the verified one-line command from the latest release notes, or download `install.sh` and inspect it before running.

## Current release

v1.11.0

- Python 3.11+
- MIT licensed
- Source archive SHA-256: `aa605b8f7f66406cc7fd1d4120b54103bad8972d9091f58c469efbe89f291042`
- Installer SHA-256: `53ede4d297e36bbf9eb09d3ce208b3283a10f2d5ecbe5286e6cb53962bce0fb9`

The Hermes compatibility layer provides the recoverable command grammar and safe local behavior documented in the source archive. Commands requiring unavailable external services or unsafe host mutation fail visibly rather than pretending to run.

## License

MIT. The release archive includes the project license, Hermes attribution, and dependency license inventory.
