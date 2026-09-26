# Computer screen (watch, take over, hand back)

Status: IMPLEMENTED (feature-flagged). Offline gates: tests/test_computer_screen.py (22 tests).
Design adapted from Nous Research hermes-agent's Bot Screen (MIT; THIRD_PARTY_NOTICES).

## What it is

The noesek-computer host can run a real desktop (TigerVNC Xvnc + Xfce) that the
agent's computer tools act on - and stream it live over a WebSocket so a human
can WATCH what the agent does, TAKE OVER when it hits a login, 2FA prompt,
CAPTCHA or payment step, then HAND CONTROL BACK. This fills roadmap item 47
(visible VM display): the X display is no longer a black box.

## Access model (safe-by-default)

- The whole surface is dark until two env vars are set: `NOESEK_SCREEN=1`
  (start Xvnc instead of Xvfb at boot) and `NOESEK_SCREEN_TOKEN` (bearer token
  gating every screen endpoint). Unset token = 503 on everything screen-shaped.
- Xvnc listens only on a 0600 Unix socket. No TCP port, no VNC password: only
  processes running as the service user can reach it; the WebSocket bridge is
  the authenticated way in.
- Viewers connect with a single-use, 30-second display ticket minted by
  `POST /computer/screen/ticket`. The ticket rides as a URL query parameter on
  purpose (noVNC cannot negotiate headers/subprotocols); a logged URL is spent
  by the time anyone reads it.

## Control lease

`src/noesek/computer/screen_lease.py` (adapted from upstream lease.py):
authority lives on disk at `$NOESEK_COMPUTER_HOME/screen/lease.json` under an
fcntl lock, because the processes that must agree do not share memory. No file
means the agent holds. A corrupt or unreadable file FAILS CLOSED (treated as
human-held) - the agent must never act on a screen a human may be using. Every
transition bumps `epoch` so an action admitted under one lease can tell control
changed underneath it. Last takeover wins; a dropped connection KEEPS the
human's control (they may be mid-login), a clean window close hands back.

While a human holds: `GET /computer/screenshot` and `POST /computer/input`
refuse with `409 human_has_control` - even screenshots, since the person may be
typing a credential. The lease is a TOOL-LEVEL fence, not an OS one: anything
the agent runs against the published DISPLAY directly (a shell) is inside the
documented same-user boundary.

## WebSocket bridge

`src/noesek/computer/screen_bridge.py` (adapted from upstream display.py):
`WS /computer/screen/ws?token=..&ticket=..` splices the RFB socket into binary
frames with backpressure both ways. The client stream passes through
`RfbClientFilter` (adapted from upstream rfb_filter.py): keyboard, pointer,
clipboard and desktop-resize messages reach Xvnc only from the lease holder;
noVNC's `viewOnly` flag is only a UI hint. The lease decision is cached 250 ms
between re-reads, and a viewer evicted by a newer takeover is closed with code
4000 `control-taken` so its UI drops to watch mode.

## Endpoints

| Route | Purpose |
|---|---|
| `GET /computer/screen` | installed/running/geometry/who holds control |
| `POST /computer/screen/start` | start Xvnc (idempotent; refuses below `NOESEK_SCREEN_MIN_FREE_MEMORY_MB`, default 512) |
| `POST /computer/screen/stop?force=` | stop; refuses while a human holds unless `force` |
| `POST /computer/screen/takeover?reason=` | human takes control; returns the `viewer_id` for input |
| `POST /computer/screen/handback?viewer_id=` | return control to the agent |
| `POST /computer/screen/ticket?viewer_id=` | mint a 30 s single-use display ticket |
| `WS /computer/screen/ws` | RFB-over-WebSocket for a noVNC viewer |

Viewer assets come from the Debian `novnc` package (image build-arg below);
a thin page at the deployment's choosing wires token + ticket into noVNC's
`websockify`-free WebSocket URL.

## Image and config

`Dockerfile.computer` build-arg `NOESEK_SCREEN=1` adds `tigervnc-standalone-server`,
minimal Xfce components and `novnc` (~900 MB layer, matching upstream's
measurement). Off by default: a plain build stays lean and nothing starts at
boot until a screen is requested. Env:

| Var | Default | Purpose |
|---|---|---|
| `NOESEK_SCREEN` | unset | `1` = start Xvnc at boot instead of Xvfb |
| `NOESEK_SCREEN_TOKEN` | unset | bearer token for all screen endpoints |
| `NOESEK_SCREEN_GEOMETRY` | `1440x900` | desktop size |
| `NOESEK_SCREEN_MIN_FREE_MEMORY_MB` | `512` | refuse to start below this (0 = never check) |

## Threat model

Same as upstream's: screens are work surfaces, not security boundaries. The RFB
socket, the X display and the lease file all belong to the service OS user; any
process running as that user can reach them directly, bypassing the lease. If
stronger isolation ever matters, the computer host must be its own OS user (or
host) per tenant. Xvnc runs `-SendCutText=0` so watchers never receive the
controlling human's clipboard; pasting INTO the screen works.
