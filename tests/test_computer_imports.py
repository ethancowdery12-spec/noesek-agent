"""The agent-first server must not pull Noesek's CLI/TUI surface.

Subprocess check: this test file itself may run inside a pytest process that
legitimately imported CLI bits for other tests.
"""
import subprocess
import sys

PROBE = """
import sys
import noesek.computer.server
bad = sorted(m for m in sys.modules
             if m.startswith("noesek") and any(k in m for k in ("tui", ".cli", ".ui")))
assert not bad, f"server import chain pulled Noesek UI modules: {bad}"
print("clean")
"""


def test_server_import_chain_has_no_noesek_ui():
    proc = subprocess.run([sys.executable, "-c", PROBE],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout[-500:] + proc.stderr[-1500:]
    assert "clean" in proc.stdout
