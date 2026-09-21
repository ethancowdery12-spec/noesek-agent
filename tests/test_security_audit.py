"""P8: security audit harness."""
from pathlib import Path

from noesek.tools.security_audit import (SecurityAuditInput, build_report,
                                         scan_source_tree, security_audit)


def _write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_detects_high_severity_probes(tmp_path):
    _write(tmp_path, "app.py", "import os, pickle\nos.system('rm -rf /')\n"
                               "data = pickle.loads(blob)\nx = eval(user_input)\n"
                               "subprocess.run(cmd, shell=True)\n")
    out = scan_source_tree(tmp_path)
    probes = {f["probe"] for f in out}
    assert {"os-system", "pickle-loads", "dynamic-exec", "shell-true"} <= probes
    assert all(f["severity"] == "high" for f in out)
    assert all(f["line"] > 0 and f["evidence"] for f in out)


def test_detects_medium_and_low(tmp_path):
    _write(tmp_path, "web.py", "requests.get(url, verify=False)\n"
                               "allow_origins=['*']\nhost = '0.0.0.0'\n"
                               "cursor.execute(f'SELECT * FROM t WHERE id={i}')\n")
    out = scan_source_tree(tmp_path)
    probes = {f["probe"] for f in out}
    assert {"tls-noverify", "cors-wildcard", "sql-fstring", "bind-all"} <= probes


def test_hardcoded_secret_flagged_but_placeholders_skipped(tmp_path):
    _write(tmp_path, "cfg.py", 'api_key = "sk-realsecretvalue123"\n'
                               'token = os.environ["TOKEN"]\n'
                               'password = "your-password-here"\n')
    out = scan_source_tree(tmp_path)
    secrets = [f for f in out if f["probe"] == "hardcoded-secret"]
    assert len(secrets) == 1
    assert "sk-realsecretvalue123" in secrets[0]["evidence"]


def test_comments_and_vendor_excluded(tmp_path):
    _write(tmp_path, "a.py", "# eval(user_input)\n")
    _write(tmp_path, "vendor/upstream/b.py", "eval(x)\n")
    out = scan_source_tree(tmp_path)
    assert out == []
    out_inc = scan_source_tree(tmp_path, include_vendor=True)
    assert len(out_inc) == 1 and out_inc[0]["file"].startswith("vendor/")


def test_report_shape_and_severity_counts(tmp_path):
    _write(tmp_path, "x.py", "eval('1')\nrequests.get(u, verify=False)\n")
    rep = build_report(tmp_path)
    assert rep["by_severity"]["high"] == 1
    assert rep["by_severity"]["medium"] == 1
    assert "1 high" in rep["summary"]
    assert rep["scope"].startswith("own layer")


async def test_security_audit_handler_on_fixture(tmp_path):
    _write(tmp_path, "y.py", "import os\nos.system('x')\n")
    out = await security_audit(SecurityAuditInput(root=str(tmp_path)))
    assert out["findings"][0]["probe"] == "os-system"


def test_security_audit_registered_on_controller():
    import inspect
    import noesek.core.controller as C
    assert '"security_audit"' in inspect.getsource(C)


def test_p9_cybersec_probes(tmp_path):
    """Roadmap item 29 probes: JWT none-alg, path concat, mktemp, weak hash, debug."""
    _write(tmp_path, "svc.py",
           "jwt.decode(tok, key, algorithms=['none'])\n"
           "f = open(base + name)\n"
           "p = tempfile.mktemp()\n"
           "h = hashlib.md5(data)\n"
           "app.run(debug=True)\n")
    out = scan_source_tree(tmp_path)
    probes = {f["probe"] for f in out}
    assert {"jwt-none", "path-concat-open", "insecure-temp", "weak-hash", "debug-enabled"} <= probes
    sev = {f["probe"]: f["severity"] for f in out}
    assert sev["jwt-none"] == "high"
