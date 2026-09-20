# Hosting the Noesek computer in the cloud for free (no credit card)

Researched 2026-09-20 (details and runners-up: docs/COMPETITIVE_MATRIX.md).
Winner: **Render free web service** - 750 instance-hours/month covers one
24/7 service, no credit card, Docker deploy, free TLS.

## One-click setup (about 3 minutes)

1. Click: [Deploy to Render](https://render.com/deploy?repo=https://github.com/ethancowdery12-spec/noesek-agent)
2. Sign in with GitHub (your usual Google -> GitHub login).
3. When prompted, paste `NOESEK_LLM_API_KEY` (your DeepSeek key). It stays in
   Render's env-var store, never in the repo or chat.
4. Deploy. When it is live, Render gives you a URL like
   `https://noesek-computer.onrender.com` - `/healthz` answers there.

## Two things to know about the free tier

- **Idle spin-down:** after 15 minutes with no inbound traffic the service
  sleeps and its local files reset. Fix: a free [UptimeRobot](https://uptimerobot.com)
  monitor (no card) hitting `https://your-app.onrender.com/healthz` every
  5 minutes keeps it awake and keeps state warm. Set that up right after deploy.
- **Ephemeral disk:** a redeploy wipes the database and connector grants.
  Fine for a trial. Render's paid persistent disk (~$1/GB) is the upgrade path
  when you want it permanent.

## What runs where

The Render service binds `0.0.0.0:$PORT` and serves the same endpoints as the
WSL2 install: `/chat`, `/computer/screenshot`, `/computer/browse`,
`/computer/input`, `/connectors/*`, `/proactive/*`. Chromium is preinstalled
in the image, so browsing works out of the box. Set
`NOESEK_CONNECTOR_GOOGLE_CLIENT_ID` / `..._SECRET` (and GitHub's) in the
Render dashboard when you create the OAuth apps; use
`https://your-app.onrender.com/connectors/callback` as the redirect URI.

## If you outgrow it

Oracle Cloud Always Free is the best free real VM (ARM, 4 cores/24GB) but
requires a credit card at signup (never charged). When you are OK with a
card, that is the upgrade; the same Dockerfile runs there unchanged.
