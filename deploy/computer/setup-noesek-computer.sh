#!/usr/bin/env bash
# Noesek computer - Linux setup (runs INSIDE WSL2 Ubuntu or any Linux VM).
# Installs the agent-first runtime + virtual display + computer tools,
# configures DeepSeek, and starts the computer as a background service.
set -euo pipefail

NOESEK_VERSION="${NOESEK_VERSION:-3.2.1}"
TARBALL_URL="https://github.com/ethancowdery12-spec/noesek-agent/releases/download/v${NOESEK_VERSION}/8-noesek-agent-v${NOESEK_VERSION}.tar.gz"
TARBALL_SHA256="${NOESEK_TARBALL_SHA256:-}"
if [ -z "$TARBALL_SHA256" ]; then
  echo "NOESEK_TARBALL_SHA256 is not set - use Install-NoesekComputer.ps1 from a released checkout." >&2
  exit 1
fi
HOME_DIR="$HOME/.noesek"
VENV="$HOME/noesek-venv"

echo "==> Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3.12 python3.12-venv xvfb scrot xdotool fonts-liberation curl ca-certificates >/dev/null

echo "==> Creating venv"
python3.12 -m venv "$VENV"
"$VENV/bin/pip" -q install --upgrade pip

echo "==> Downloading noesek-agent v${NOESEK_VERSION}"
cd /tmp
curl -fsSL -o noesek.tar.gz "$TARBALL_URL"
echo "$TARBALL_SHA256  noesek.tar.gz" | sha256sum -c -
"$VENV/bin/pip" -q install noesek.tar.gz

echo "==> Installing Chromium for the browser tool"
sudo "$VENV/bin/playwright" install-deps chromium >/dev/null
"$VENV/bin/playwright" install chromium >/dev/null

echo "==> Writing config"
mkdir -p "$HOME_DIR"
if [ ! -f "$HOME_DIR/computer.env" ]; then
  API_SERVER_KEY_LOCAL="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  cat > "$HOME_DIR/computer.env" <<ENVEOF
NOESEK_HOME=$HOME_DIR
NOESEK_DATABASE_URL=sqlite+aiosqlite:///$HOME_DIR/noesek.db
NOESEK_LLM_BASE_URL=${NOESEK_LLM_BASE_URL:-https://api.deepseek.com/v1}
NOESEK_LLM_API_KEY=${NOESEK_LLM_API_KEY:-}
NOESEK_LLM_MODEL=${NOESEK_LLM_MODEL:-deepseek-chat}
NOESEK_COMPUTER_PORT=8780
NOESEK_COMPUTER_DISPLAY=:99
ENVEOF
  chmod 600 "$HOME_DIR/computer.env"
fi

echo "==> Installing service"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/noesek-computer.service" <<SVCEOF
[Unit]
Description=Noesek computer (agent-first runtime)
After=network-online.target

[Service]
EnvironmentFile=$HOME_DIR/computer.env
ExecStart=$VENV/bin/noesek-computer
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
SVCEOF
(systemctl --user daemon-reload && systemctl --user enable --now noesek-computer.service) 2>/dev/null || \
  echo "NOTE: systemd user services unavailable - start with: noesek-computer (or use the .service on a VM with systemd)"

echo "==> Self-test"
set -a; . "$HOME_DIR/computer.env"; set +a
"$VENV/bin/noesek" doctor | head -20 || true
echo
echo "Done. The computer answers chats at http://127.0.0.1:8780/chat"
echo 'Test:  curl -s -X POST http://127.0.0.1:8780/chat -H "Content-Type: application/json" -d '"'"'{"chat_id":"me","text":"hi"}'"'"
