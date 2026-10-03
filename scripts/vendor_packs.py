#!/usr/bin/env python3
"""Copy vendored third-party reference packs byte for byte and verify every hash.

Each pack dir under src/noesek/data (agent_pack, packs/*) has a manifest.json naming the upstream
repo, the pinned commit, the license file hash and every file's source path, destination, sha256 and
size. This script fetches the pinned commit (or a local copy given by --source-map), checks the
license and every file against the manifest, and writes files only when ALL of a pack verifies.
Any mismatch exits non-zero and writes nothing for that pack. It never executes vendored content.
Usage: python scripts/vendor_packs.py [--source-map map.json] [--check]
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
DATA=Path('src/noesek/data')

def pack_dirs():
    return sorted([p for p in [DATA/'agent_pack',*sorted((DATA/'packs').glob('*'))] if (p/'manifest.json').is_file()])

def sha(raw):return hashlib.sha256(raw).hexdigest()

def fetch(repo,commit,cache,source_map):
    if repo in source_map:return Path(source_map[repo])
    if repo in cache:return cache[repo]
    dest=Path(tempfile.mkdtemp(prefix='vendor-'))/'up'
    subprocess.run(['git','clone','--quiet',repo,str(dest)],check=True)
    subprocess.run(['git','-C',str(dest),'checkout','--quiet',commit],check=True)
    head=subprocess.run(['git','-C',str(dest),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    if head!=commit:raise SystemExit(f'{repo}: checked out {head}, expected {commit}')
    cache[repo]=dest;return dest

def plan(pack,source):
    man=json.loads((pack/'manifest.json').read_text(encoding='utf-8'))
    lic=(source/man.get('license_src','LICENSE')).read_bytes()
    if sha(lic)!=man['license_sha256']:return None,[f'{pack.name}: license hash mismatch']
    writes=[(pack/'LICENSE',lic)];bad=[]
    for f in man['files']:
        raw=(source/f['src']).read_bytes()
        if sha(raw)!=f['sha256'] or len(raw)!=f['bytes']:bad.append(f"{pack.name}: {f['src']}");continue
        writes.append((pack/f['dest'],raw))
    return (None if bad else writes),bad

def main(argv):
    source_map={};check='--check' in argv
    if '--source-map' in argv:source_map=json.loads(Path(argv[argv.index('--source-map')+1]).read_text())
    cache={};failed=False
    for pack in pack_dirs():
        man=json.loads((pack/'manifest.json').read_text(encoding='utf-8'))
        try:source=fetch(man['repo'],man['commit'],cache,source_map)
        except Exception as exc:print(f'{pack.name}: fetch failed: {exc}');failed=True;continue
        writes,bad=plan(pack,source)
        if writes is None:print('MISMATCH',bad[:10]);failed=True;continue
        if not check:
            for path,raw in writes:
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        print(f'{pack.name}: verified {len(writes)-1} files + license byte-exact'+(' (check only)' if check else ''))
    return 1 if failed else 0

if __name__=='__main__':sys.exit(main(sys.argv[1:]))
