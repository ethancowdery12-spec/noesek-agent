# Noesek computer vs the field (September 2026)

Sources are live product pages and launch posts, fetched 2026-09-20:
- OpenAI Codex: https://openai.com/codex/
- Claude Cowork (now merged into one Claude): https://claude.com/blog/cowork-is-now-claude and https://claude.com/product/cowork
- Perplexity Computer: https://www.perplexity.ai/hub/blog/introducing-perplexity-computer and https://www.perplexity.ai/products/computer
- Instinct column: Ethan's own Instinct assistant's user-visible capabilities (as he listed them).

Legend: yes / partial / no. "Noesek" = the Noesek computer at v3.2.0 + merged post-release work.

| Capability | Noesek computer | Instinct | Codex (ChatGPT) | Claude (Cowork) | Perplexity Computer |
|---|---|---|---|---|---|
| Messaging-native chats (WhatsApp/iMessage-style) | yes (WhatsApp/Slack/Telegram webhooks; chats are sessions) | yes | partial (Slack via workspace agents) | partial (app + mobile, no WhatsApp) | no (app only) |
| Chats = durable sessions | yes | yes | partial (tasks) | yes (projects) | yes (threads) |
| Persistent memory of the user | yes (local keyword memory) | yes | partial (skills, repo context) | yes | yes |
| Computer use: screenshots + browser | yes (Xvfb + scrot + Chromium, approval contract) | yes (cloud browser) | partial (cloud dev environments) | yes (computer use) | yes (isolated env, real browser) |
| Full desktop control (mouse/keyboard input) | partial (xdotool installed, no endpoint yet) | yes | no | yes | yes |
| OAuth connectors to user services | yes (Google + GitHub, full OAuth loop, chat-scoped grants) | yes (Gmail/Calendar/Drive/Slack/GitHub/...) | yes (GitHub deep) | yes (connector directory) | yes (connected services) |
| Agent can read connected services | yes (gmail_read, calendar_read, github_notifications as chat tools) | yes | yes (repos) | yes | yes |
| Agent can write/send as the user | no (read-only by design, waiting on Ethan) | yes (with approval) | partial (PRs) | partial | partial |
| Proactive / scheduled work | yes (activate/pause/tick, IDLE withheld) | yes (scheduled wakes, event watches) | yes (scheduled background tasks) | yes ("schedule it for every Monday") | yes (tasks) |
| Sub-agent delegation | yes (thin controller -> workers, SpawnGrant) | yes | yes (parallel cloud agents, worktrees) | yes (subagents) | yes (signature: sub-agents per task) |
| Multi-model orchestration | no (single provider, deliberate - Ethan's call) | yes | no (OpenAI only) | no (Anthropic only) | yes (Opus core + Gemini/Grok/ChatGPT/Nano Banana/Veo per task) |
| Voice notes | no (planned v4.2) | yes | no | yes (voice mode) | yes |
| File creation & delivery (docs/slides) | no | yes (files delivered in chat) | partial (code artifacts) | yes (Docs, Slides, Design) | yes (document generation) |
| Mobile app channel | partial (WhatsApp is the mobile channel; no own app) | yes | yes (ChatGPT app) | yes | yes |
| Secrets vault | no (env vars only) | yes | n/a | n/a | n/a |
| Payments / purchases | no | yes (Link) | no | no | no |
| Runs on your own machine (private, your keys) | yes (WSL2 one-liner; nothing leaves the box) | no (cloud) | no | no | no |
| Open source / self-hostable | yes (MIT) | no | partial (CLI) | partial (Code) | no |
| Approval / safety contract | yes (plan/digest, origin allowlists) | yes | yes | yes (check-in preferences) | partial |
| Long-running async work (hours+) | partial (tasks queue; no month-long harness yet) | yes | yes (cloud envs) | yes (works after laptop closed) | yes (hours to months) |

## What we're missing (the honest gap list), in implementation order

1. **Desktop input endpoint** (`/computer/input` - xdotool click/type/key on the virtual display). Every competitor with computer use has full control; we only have look, not touch. Small, high value.
2. **Secrets vault on the VM** - one 0600 store + endpoints, so OAuth client secrets and API keys stop living in env vars. Instinct has this; every serious agent box needs it.
3. **Write/send connector actions behind the approval contract** (gmail_send first). Read-only was a design pause, not a moat. Plan/digest approval already exists - sends ride it, default ask-first.
4. **File creation & delivery** (`/files` - author markdown/docx, serve back a download link). Claude Docs/Slides and Perplexity document generation set the bar; this is how the computer hands work back.
5. **Voice notes** (`/voice/say` offline TTS first - piper/espeak-ng, no API cost; STT ingest later). Instinct, Claude, Perplexity all talk.
6. **Long-running task harness** - our queue runs tasks; Perplexity runs workflows for months. Gap is durability guarantees (checkpoint/resume), not concept.
7. **Multi-model orchestration** - DOCUMENTED DIVERGENCE, not a gap to fill: Ethan locked single-provider, no fallback. Perplexity's multi-model harness is their signature; ours is cost discipline on one key. Revisit only if Ethan unlocks it.
8. **Own mobile app** - v4.2 research item; WhatsApp covers the channel meanwhile.

## Hosting the agent for free, no credit card (researched 2026-09-20)

| Option | Always-on? | Card required? | Verdict |
|---|---|---|---|
| **Render free web service** | 750 instance-hours/month = one 24/7 service (744h) | **No** | **Winner.** Docker deploy, free TLS, one-click blueprint button. Caveats: spins down after 15 min idle (keep-awake ping fixes), filesystem is ephemeral (state resets on redeploy/spin-down - fine for a trial; paid disk is the upgrade path) |
| Oracle Cloud Always Free | yes (real VM, ARM Ampere) | **Yes** (required at signup, not charged) | Best free VM on the internet, but fails Ethan's no-card rule |
| Koyeb free instance | 512MB nano | **Yes** ($29 pre-auth + pro-rated charge) | Out |
| Fly.io | - | Yes | Out |
| Railway | trial credit only | - | Not sustainable 24/7 |
| Cloudflare Workers | always on, no card | No | Not a VM - can't run our FastAPI+Xvfb+Chromium stack |
| GitHub Codespaces / Ona | no (hours-capped dev envs) | no | Not hosting |

Setup for Render is one click: the repo ships `render.yaml` + `Dockerfile.computer`, so the
"Deploy to Render" button (docs/HOSTING.md) walks him through sign-in with GitHub (he already
uses Google->GitHub), one env var (`NOESEK_LLM_API_KEY`), done. Keep-awake: free UptimeRobot
monitor hitting `/healthz` every 5 minutes (no card, keeps state warm).
