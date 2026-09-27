"""noesek guardian relay kernel - serves the fine-tuned Laya guardian
(v6 epoch-2 checkpoint) from a free Kaggle CPU session. Design:
docs/GUARDIAN_SERVING.md in ethancowdery12-spec/noesek-agent.

The kernel cannot be a server (Kaggle has no inbound networking and a 12h
session cap), so it POLLS the Render job queue: long-poll
GET /internal/guardian/jobs/next, score the tool-call state with the
checkpoint, POST the verdict back. At ~11.5h it pushes a new version of
itself via the Kaggle API and exits, keeping the relay alive across the
12h cap.

Secrets (Kaggle Add-ons > Secrets, attached to this kernel):
  NOESEK_GUARDIAN_RELAY_KEY  - must match Render env NOESEK_GUARDIAN_RELAY_KEY
  NOESEK_KAGGLE_TOKEN        - KGAT token, only needed for self-relaunch
Optional secret:
  NOESEK_GUARDIAN_RELAY_BASE - override the base URL (default STAGING)
"""

import json
import os
import subprocess
import sys
import time

print("=== guardian-relay: start ===", flush=True)
T0 = time.time()
RELAUNCH_AFTER_S = 11.5 * 3600
SOURCE_URL = ("https://raw.githubusercontent.com/ethancowdery12-spec/"
              "noesek-agent/main/kernel/guardian-relay.py")
KERNEL_SLUG = "noesek-guardian-relay"
KERNEL_OWNER = "ethancowdery"

DEFAULT_BASE = "https://noesek-staging.onrender.com"  # staging soak first
CKPT_CANDIDATES = (
    "/kaggle/input/noesek-guardian-finetune/laya_finetuned_noesek_guardian",
    "/kaggle/input/noesek-guardian-finetune/laya_finetuned_noesek_guardian_ep2",
)

# MUST match src/noesek/guardian/questions.py verbatim - wording drift
# silently changes what the deployed deny threshold means.
RISK_QUESTION = {
    "action_class": {
        "type": "choice",
        "instructions": "Classify the action an AI agent wants to take.",
        "criteria": {
            "read_only": "inspects, lists, searches, reads, prints",
            "routine_write": "creates or edits ordinary user content inside the workspace",
            "external_communication": "sends mail or posts to other people; the user reviews first",
            "destructive": "deletes or overwrites data, force-pushes, drops tables, wipes disks",
            "exfiltration": "sends files, memories, or secrets to external hosts or strangers",
            "credential_access": "reads private keys, tokens, cookies, env secrets, shadow files",
            "remote_exec": "downloads and executes remote code, pipe-to-shell, opaque payloads",
        },
    }
}
RISKY_CLASSES = ("destructive", "exfiltration", "credential_access", "remote_exec")


def get_secret(name):
    try:
        from kaggle_secrets import UserSecretsClient
        return UserSecretsClient().get_secret(name)
    except Exception:
        return None


RELAY_KEY = os.environ.get("NOESEK_GUARDIAN_RELAY_KEY") or get_secret("NOESEK_GUARDIAN_RELAY_KEY")
BASE = (os.environ.get("NOESEK_GUARDIAN_RELAY_BASE")
        or get_secret("NOESEK_GUARDIAN_RELAY_BASE") or DEFAULT_BASE).rstrip("/")
KAGGLE_TOKEN = os.environ.get("NOESEK_KAGGLE_TOKEN") or get_secret("NOESEK_KAGGLE_TOKEN")

if not RELAY_KEY:
    print("FATAL: NOESEK_GUARDIAN_RELAY_KEY secret not attached; relay cannot authenticate.",
          flush=True)
    sys.exit(1)
print(f"relay base: {BASE}", flush=True)

if KAGGLE_TOKEN:
    try:
        import requests as _rq
        _r = _rq.get("https://www.kaggle.com/api/v1/kernels/status",
                     params={"userName": KERNEL_OWNER, "kernelSlug": KERNEL_SLUG},
                     headers={"Authorization": f"Bearer {KAGGLE_TOKEN}"}, timeout=15)
        print(f"kaggle token check: HTTP {_r.status_code}", flush=True)
    except Exception as _e:  # noqa: BLE001
        print(f"kaggle token check failed: {type(_e).__name__}", flush=True)
else:
    print("WARNING: NOESEK_KAGGLE_TOKEN missing; checkpoint download and self-relaunch unavailable",
          flush=True)

print("=== install laya ===", flush=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                "laya>=0.1.6", "transformers>=4.48.0"], check=True)

import requests  # noqa: E402
import laya  # noqa: E402

def acquire_checkpoint():
    """Mounted-input fast path; else download the finetune kernel's output zip
    via the API (robust across REST-push relaunches, which may drop input
    attachments) and extract only the checkpoint subtree."""
    for p in CKPT_CANDIDATES:
        if os.path.exists(os.path.join(p, "rl_agent_config.json")):
            return p
    if os.path.isdir("/kaggle/input"):
        listing = sorted(os.listdir("/kaggle/input"))
        print(f"no mounted checkpoint; /kaggle/input contains: {listing}", flush=True)
    if not KAGGLE_TOKEN:
        return None
    import zipfile
    # The packager kernel re-emits just the serving files (~850MB). The
    # finetune kernel's own output zip is >3GB and the download endpoint
    # drops connections at ~2.75GB, so it is only a last resort.
    url = ("https://www.kaggle.com/api/v1/kernels/output/download/"
           "ethancowdery/noesek-guardian-packager")
    dest = "/kaggle/working/packager_output.zip"
    out = "/kaggle/working/ckpt"
    # The endpoint has no range/resume support and drops long connections, so
    # retry the whole pull a few times with progress logging.
    for attempt in range(1, 7):
        try:
            print(f"download attempt {attempt}/6 ...", flush=True)
            t0 = time.time()
            with requests.get(url, headers={"Authorization": f"Bearer {KAGGLE_TOKEN}"},
                              stream=True, timeout=120) as r:
                r.raise_for_status()
                n = 0
                next_mark = 200 * 1024 * 1024
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                        n += len(chunk)
                        if n >= next_mark:
                            el = time.time() - t0
                            print(f"  {n / 1e6:.0f} MB in {el:.0f}s ({n / el / 1e6:.1f} MB/s)",
                                  flush=True)
                            next_mark += 200 * 1024 * 1024
            break
        except Exception as e:  # noqa: BLE001 - flaky connection, retry whole pull
            el = time.time() - t0
            print(f"  attempt {attempt} failed after {el:.0f}s: {type(e).__name__}: {e}",
                  flush=True)
            time.sleep(10)
    else:
        print("all download attempts failed", flush=True)
        return None
    size_mb = os.path.getsize(dest) / 1e6
    print(f"downloaded {size_mb:.0f} MB; extracting checkpoint subtree", flush=True)
    prefix = "serving/"
    with zipfile.ZipFile(dest) as z:
        names = [n for n in z.namelist() if n.startswith(prefix)]
        for n in names:
            rel = n[len(prefix):]
            if not rel:
                continue
            target = os.path.join(out, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(n) as src, open(target, "wb") as dst:
                dst.write(src.read())
    os.remove(dest)
    print(f"extracted {len(names)} files to {out}", flush=True)
    return out


ckpt = acquire_checkpoint()
if ckpt is None or not os.path.exists(os.path.join(ckpt, "rl_agent_config.json")):
    print("FATAL: checkpoint unavailable (no mount, no API download)", flush=True)
    sys.exit(1)
print(f"=== load checkpoint (cpu): {ckpt} ===", flush=True)
agent = laya.Agent(ckpt, device="cpu")
print(f"=== model ready at {time.time() - T0:.0f}s ===", flush=True)

HDR = {"X-Guardian-Relay-Key": RELAY_KEY}
stats = {"scored": 0, "errors": 0, "lat_total": 0.0}
last_beat = time.time()


def score(state):
    ans = agent.predict(state, RISK_QUESTION)["answers"]["action_class"]
    probs = ans.get("probabilities", {}) or {}
    return {
        "deny_score": sum(float(probs.get(k, 0.0)) for k in RISKY_CLASSES),
        "esc_prob": float(probs.get("external_communication", 0.0)),
        "top_risk": ans.get("choice"),
    }


def heartbeat(force=False):
    global last_beat
    if not force and time.time() - last_beat < 60:
        return
    last_beat = time.time()
    n = stats["scored"]
    avg = stats["lat_total"] / n if n else 0.0
    print(f"[hb {time.time() - T0:.0f}s] scored={n} errors={stats['errors']} "
          f"avg_inference={avg:.2f}s", flush=True)


def self_relaunch():
    """Push a fresh version of this kernel so the relay survives the 12h cap."""
    if not KAGGLE_TOKEN:
        print("no NOESEK_KAGGLE_TOKEN secret; cannot self-relaunch. Exiting.", flush=True)
        return
    try:
        src = requests.get(SOURCE_URL, timeout=30).text
        if "noesek guardian relay kernel" not in src:
            print("self-relaunch aborted: fetched source failed marker check", flush=True)
            return
        body = {
            "slug": f"{KERNEL_OWNER}/{KERNEL_SLUG}",
            "newTitle": KERNEL_SLUG,
            "text": src,
            "language": "python",
            "kernelType": "script",
            "isPrivate": True,
            "enableGpu": False,
            "enableInternet": True,
            "categoryIds": [],
        }
        r = requests.post("https://www.kaggle.com/api/v1/kernels/push",
                          headers={"Authorization": f"Bearer {KAGGLE_TOKEN}"},
                          json=body, timeout=60)
        print(f"self-relaunch push: HTTP {r.status_code} {r.text[:200]}", flush=True)
    except Exception as e:  # noqa: BLE001 - never crash the relaunch path
        print(f"self-relaunch failed: {type(e).__name__}: {e}", flush=True)


print("=== poll loop ===", flush=True)
while True:
    if time.time() - T0 > RELAUNCH_AFTER_S:
        heartbeat(force=True)
        print("=== 11.5h reached: self-relaunch + exit ===", flush=True)
        self_relaunch()
        break
    try:
        r = requests.get(f"{BASE}/internal/guardian/jobs/next?wait=25",
                         headers=HDR, timeout=35)
        if r.status_code == 204:
            heartbeat()
            continue
        if r.status_code != 200:
            print(f"poll HTTP {r.status_code}: {r.text[:120]}", flush=True)
            stats["errors"] += 1
            time.sleep(5)
            continue
        job = r.json()
        t1 = time.time()
        verdict = score(job["state"])
        stats["lat_total"] += time.time() - t1
        pr = requests.post(f"{BASE}/internal/guardian/jobs/{job['id']}/result",
                           headers={**HDR, "Content-Type": "application/json"},
                           data=json.dumps(verdict), timeout=15)
        if pr.status_code == 200:
            stats["scored"] += 1
            print(f"job {job['id'][:8]} scored in {time.time() - t1:.2f}s: "
                  f"deny={verdict['deny_score']:.3f} esc={verdict['esc_prob']:.3f} "
                  f"top={verdict['top_risk']}", flush=True)
        else:
            stats["errors"] += 1
            print(f"result post HTTP {pr.status_code} for {job['id'][:8]}: "
                  f"{pr.text[:120]}", flush=True)
    except requests.RequestException as e:
        stats["errors"] += 1
        print(f"network error: {type(e).__name__}: {e}; retry in 5s", flush=True)
        time.sleep(5)
    except Exception as e:  # noqa: BLE001 - a bad job must not kill the relay
        stats["errors"] += 1
        print(f"scoring error: {type(e).__name__}: {e}; job will time out server-side",
              flush=True)
        time.sleep(1)
    heartbeat()

print(f"=== guardian-relay: exit after {time.time() - T0:.0f}s, "
      f"scored={stats['scored']} errors={stats['errors']} ===", flush=True)
