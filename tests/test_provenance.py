"""License, provenance, and supply-chain guards for the vendored upstream tree."""
import hashlib
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor/hermes-agent"
MANIFEST = ROOT / "vendor/VENDOR_PROVENANCE.sha256"
PIN = "d7b836ab1c0cddaafc109ed24c9a83b6191cdc88"


def _manifest_rows():
    rows = {}
    for line in MANIFEST.read_text().splitlines():
        if line.startswith("#") or not line.strip() or "  " not in line:
            continue
        # sha256sum prefixes lines with a backslash when the filename needs escaping
        line = line.lstrip("\\")
        h, rel = line.split("  ", 1)
        rows[rel.strip()] = h.strip()
    return rows


def test_license_file_present_and_mit():
    text = (VENDOR / "LICENSE").read_text()
    assert "MIT License" in text and "Nous Research" in text


def test_manifest_header_pins_commit():
    head = "\n".join(MANIFEST.read_text().splitlines()[:8])
    assert PIN in head
    assert "https://github.com/NousResearch/hermes-agent" in head


def test_manifest_is_complete_over_the_tree():
    rows = _manifest_rows()
    on_disk = {str(p.relative_to(VENDOR)) for p in VENDOR.rglob("*") if p.is_file()}
    assert set(rows) == on_disk
    assert len(rows) == 14189


def test_sampled_file_hashes_match_manifest():
    rows = _manifest_rows()
    sample = random.Random(20260919).sample(sorted(rows), 25)
    for rel in sample:
        digest = hashlib.sha256((VENDOR / rel).read_bytes()).hexdigest()
        assert digest == rows[rel], rel
