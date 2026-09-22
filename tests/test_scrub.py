"""Tests for the metadata-hygiene scrub tool (roadmap item 48)."""
import io
import zipfile

import pytest

from noesek import filestore
from noesek.tools.scrub import scrub_text, scrub_file


@pytest.fixture(autouse=True)
def tmp_files(monkeypatch, tmp_path):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    yield


def test_text_strips_invisible_classes():
    text = "he​llo‍wor​ld⁠­‎﻿"
    out = scrub_text(text)
    assert out["text"] == "helloworld"
    assert out["removed"] == 7
    assert set(out["by_class"]) == {"zero_width", "soft_hyphen", "bidi_controls", "byte_order_mark"}


def test_text_strips_tag_characters():
    out = scrub_text("a\U000e0045b\U000e0067c")
    assert out["text"] == "abc"
    assert out["by_class"] == {"tag_characters": 2}


def test_text_preserves_visible_typography():
    visible = "em—dash “curly” nbsp  é\nline two"
    out = scrub_text(visible)
    assert out["text"] == visible
    assert out["removed"] == 0


def test_missing_file_errors():
    with pytest.raises(filestore.FileStoreError):
        scrub_file("nope.png")


def test_text_file_scrubbed_to_clean_copy():
    filestore.write_file("notes.txt", "abc​def")
    name, cleaned, removed = scrub_file("notes.txt")
    assert name == "notes-clean.txt"
    assert cleaned == b"abcdef"
    assert any("zero_width" in r for r in removed)
    # original untouched
    assert filestore.read_file("notes.txt") == "abc​def".encode()


def _make_docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.main"/>'
                   '<Override PartName="/docProps/core.xml" ContentType="application/vnd.core-properties+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                   '</Relationships>')
        z.writestr("docProps/core.xml", "<coreProperties><dc:creator>someone</dc:creator></coreProperties>")
        z.writestr("word/document.xml", "<document><body>Hello</body></document>")
    return buf.getvalue()


def test_office_docprops_stripped_document_intact():
    filestore.write_file("report.docx", _make_docx())
    name, cleaned, removed = scrub_file("report.docx")
    assert name == "report-clean.docx"
    assert any("docProps/core.xml" in r for r in removed)
    z = zipfile.ZipFile(io.BytesIO(cleaned))
    assert "docProps/core.xml" not in z.namelist()
    assert z.read("word/document.xml") == b"<document><body>Hello</body></document>"
    assert b"docProps" not in z.read("_rels/.rels")
    assert b"/docProps/" not in z.read("[Content_Types].xml")


def test_image_exif_stripped_pixels_kept():
    from PIL import Image
    img = Image.new("RGB", (4, 3), (200, 30, 30))
    exif = Image.Exif()
    exif[271] = "TestCamera"  # Make
    buf = io.BytesIO()
    img.save(buf, format="PNG", exif=exif)
    filestore.write_file("photo.png", buf.getvalue())
    name, cleaned, removed = scrub_file("photo.png")
    assert name == "photo-clean.png"
    out = Image.open(io.BytesIO(cleaned))
    assert out.size == (4, 3)
    assert not out.info.get("exif")
    assert list(out.getdata())[0] == (200, 30, 30)


def test_pdf_graceful_without_pypdf():
    pytest.importorskip("sys")
    try:
        import pypdf  # noqa: F401
        pytest.skip("pypdf installed - graceful path not applicable")
    except ImportError:
        pass
    filestore.write_file("doc.pdf", b"%PDF-1.4 fake")
    with pytest.raises(filestore.FileStoreError, match="pypdf"):
        scrub_file("doc.pdf")


def test_unsupported_extension_errors():
    filestore.write_file("data.bin", b"\x00\x01")
    with pytest.raises(filestore.FileStoreError, match="unsupported"):
        scrub_file("data.bin")


from noesek.tools.naturalize import rewrite_natural_text


def test_rewrite_natural_cuts_hedges_and_openers():
    out = rewrite_natural_text(
        "It is important to note that this may potentially work. Furthermore, it plays a crucial role in results.")
    assert "important to note" not in out["text"]
    assert "may potentially" not in out["text"]
    assert "Furthermore" not in out["text"]
    assert "is central to results" in out["text"]
    assert out["text"][0].isupper()
    assert len(out["applied"]) >= 3


def test_rewrite_natural_preserves_facts_and_names():
    out = rewrite_natural_text("Ethan shipped PR 97 on September 21, 2026 at 6:37 PM.")
    assert "Ethan" in out["text"] and "PR 97" in out["text"] and "September 21, 2026" in out["text"]


def test_rewrite_natural_flags_uniform_rhythm():
    out = rewrite_natural_text("Cats sleep all day long. Dogs run around the park. Birds fly over the trees. Fish swim under the waves.")
    assert out["structure"].get("rhythm")


def test_rewrite_natural_clean_text_untouched():
    text = "Ship it Friday. If CI stays green we merge, otherwise we wait."
    out = rewrite_natural_text(text)
    assert out["text"] == text


def test_rewrite_natural_role_in_gerund_not_stranded():
    # Live-test catch: "plays a crucial role in driving X" must not become "drives driving X".
    out = rewrite_natural_text("It plays a crucial role in driving seamless innovation.")
    assert "drives driving" not in out["text"]
    assert "is central to driving" in out["text"]


def test_rewrite_natural_delve_family():
    out = rewrite_natural_text("We delved into the data. She delves deep. They are delving now.")
    assert "dug into" in out["text"] and "digs deep" in out["text"] and "digging" in out["text"]
    assert "delve" not in out["text"].lower()
