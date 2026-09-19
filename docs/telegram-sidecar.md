# Telegram sidecar: operator-owned process boundary

Telegram runs as a sidecar process, not inside the Noesek core, because
aiogram caps pydantic below Noesek's exact pin (aiogram requires
pydantic <2.13; Noesek pins pydantic==2.13.5). Exact pins win over
convenience, so the Telegram bot lives in its own interpreter.

## Topology

    Telegram API  <--polling/webhook--  sidecar (sidecars/telegram_bot.py)
                                            |
                                            | HTTP POST /webhooks/telegram
                                            | header: X-Telegram-Bot-Api-Secret-Token
                                            v
                                     Noesek core (authorization gate ->
                                     controller -> workers)

## Ownership boundaries

- The sidecar owns: the Telegram bot token (NOESEK_TELEGRAM_BOT_TOKEN in the
  sidecar environment only), Telegram API retry/backoff, and update intake
  (polling loop or webhook receiver).
- The core owns: authorization (pairing store + gate), conversation state,
  the controller, workers, and all policy decisions. The core never holds
  the bot token.
- The shared secret (NOESEK_TELEGRAM_WEBHOOK_SECRET) authenticates the
  sidecar to the core. It must be identical in both environments and is
  operator-managed (vault or env file with 0600 permissions).

## Process supervision (operator-owned)

The operator's process supervisor owns the sidecar lifecycle. Example
systemd unit:

    [Unit]
    Description=Noesek Telegram sidecar
    After=network-online.target noesek.service

    [Service]
    EnvironmentFile=/etc/noesek/telegram.env   # 0600, operator-managed
    ExecStart=/usr/bin/python3 /opt/noesek/sidecars/telegram_bot.py
    Restart=on-failure
    RestartSec=5
    # Sidecar has its own venv with aiogram; do NOT share the core venv.

    [Install]
    WantedBy=multi-user.target

- Restart policy: on-failure with backoff; Telegram's getUpdates is
  idempotent (offset-tracked), so restarts never double-deliver; the core's
  controller dedups repeated update_ids regardless.
- Health: the sidecar exits nonzero when the core webhook returns repeated
  401s (secret mismatch) or is unreachable beyond the backoff window; the
  supervisor's own alerting picks that up.
- Upgrades: restart the sidecar any time; in-flight updates are re-fetched
  from Telegram after restart. Core deploys require no sidecar coordination
  as long as /webhooks/telegram keeps its contract (secret-token header,
  update JSON, {"ok": true} response).
