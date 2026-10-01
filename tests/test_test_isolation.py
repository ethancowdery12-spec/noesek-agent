"""Configuration import must never select the checkout DB in a bare test run."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_conftest_isolates_before_configuration_imports(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    sentinel = tmp_path / "noesek.db"
    sentinel.write_bytes(b"untouched-user-db")
    env = {k: v for k, v in os.environ.items() if k not in {
        "NOESEK_DATABASE_URL", "NOESEK_HOME", "HERMES_HOME", "NOESEK_CODE_INTEL_DB"}}
    env["PYTHONPATH"] = str(repo / "src")
    code = f'''import runpy,json
runpy.run_path({str(repo / "tests/conftest.py")!r})
from noesek.config import settings
from noesek.db import engine
print(json.dumps({{"configured":settings.database_url,"engine":str(engine.url)}}))
'''
    proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.splitlines()[-1])
    for url in result.values():
        assert "noesek-test-" in url and url.endswith("/test.db")
    assert sentinel.read_bytes() == b"untouched-user-db"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["noesek.db"]
