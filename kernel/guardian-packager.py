"""noesek guardian checkpoint packager (one-shot Kaggle CPU kernel).

The finetune kernel's output zip is >3GB and Kaggle's output-download
endpoint drops long connections at ~2.75GB, so the serving checkpoint
(which sorts late in that zip) cannot be fetched directly. This kernel
mounts the finetune kernel as an INPUT (server-side, no size cap) and
re-emits ONLY the files the relay needs to serve, so its own output zip
is ~850MB and downloads cleanly.

Attach input: ethancowdery/noesek-guardian-finetune (editor UI Add Input).
"""
import hashlib
import os
import shutil

print("=== packager: input tree ===", flush=True)
SRC = None
for root, dirs, files in os.walk("/kaggle/input"):
    depth = root.count(os.sep)
    if depth <= 4:
        print(f"  {root} ({len(files)} files)", flush=True)
    if os.path.basename(root) == "laya_finetuned_noesek_guardian":
        SRC = root
    if depth > 5:
        dirs[:] = []

if SRC is None:
    print("FATAL: no laya_finetuned_noesek_guardian dir under /kaggle/input", flush=True)
    raise SystemExit(1)
print(f"SRC = {SRC}", flush=True)

DST = "/kaggle/working/serving"
if os.path.exists(DST):
    shutil.rmtree(DST)
os.makedirs(DST)

copied = []
for root, dirs, files in os.walk(SRC):
    if "checkpoint_latest" in root.split(os.sep):
        continue
    for fn in files:
        s = os.path.join(root, fn)
        rel = os.path.relpath(s, SRC)
        d = os.path.join(DST, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        copied.append((rel, os.path.getsize(d)))

total = sum(sz for _, sz in copied)
print(f"copied {len(copied)} files, {total / 1e6:.0f} MB total", flush=True)
for rel, sz in sorted(copied):
    print(f"  {rel}: {sz / 1e6:.1f} MB", flush=True)

if not copied:
    print("FATAL: copied 0 files", flush=True)
    raise SystemExit(1)

h = hashlib.sha256()
with open(os.path.join(DST, "model.safetensors"), "rb") as f:
    for chunk in iter(lambda: f.read(1 << 22), b""):
        h.update(chunk)
print(f"model.safetensors sha256: {h.hexdigest()}", flush=True)
assert os.path.exists(os.path.join(DST, "rl_agent_config.json")), "config missing"
print("packager done", flush=True)
