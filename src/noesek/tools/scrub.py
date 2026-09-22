"""Metadata hygiene for the user's own files and text (roadmap item 48).

Ethan asked for "AI watermark removal". The approved scope is hygiene on
HIS OWN content, on request: strip invisible Unicode provenance markers
from text, and strip metadata (EXIF, document properties) from his own
images and Office files. Detection evasion - making AI-generated output
undetectable to classifiers, or disguising the provenance of content for
third parties - is out of scope by policy and is not implemented here.

Deterministic, no model call, no new dependencies: image scrub uses the
already-pinned Pillow; Office scrub uses stdlib zipfile + XML; PDF scrub
activates only if pypdf is installed, and says so plainly when it is not.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field

from .. import filestore


class ScrubInput(BaseModel):
    text: str | None = Field(default=None, max_length=filestore.MAX_FILE_BYTES,
                             description="Text to clean of invisible watermark characters")
    file: str | None = Field(default=None,
                             description="Name of a file in the download store to clean (image, Office doc, PDF, or text file)")


# Invisible Unicode classes commonly used as AI/provenance watermarks.
_INVISIBLE_CLASSES = {
    "zero_width": ["\u200b", "\u200c", "\u200d", "\u2060", "\u180e"],
    "soft_hyphen": ["\u00ad"],
    "bidi_controls": ["\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
                      "\u2066", "\u2067", "\u2068", "\u2069"],
    "byte_order_mark": ["\ufeff"],
}
_TAG_RE = re.compile(r"[\U000E0000-\U000E007F]")  # Unicode tag block (invisible annotation chars)


def scrub_text(text: str) -> dict:
    """Remove invisible watermark characters; visible text is never touched."""
    by_class: dict[str, int] = {}
    out = text
    for cls, chars in _INVISIBLE_CLASSES.items():
        n = sum(out.count(c) for c in chars)
        if n:
            by_class[cls] = n
            for c in chars:
                out = out.replace(c, "")
    tags = _TAG_RE.findall(out)
    if tags:
        by_class["tag_characters"] = len(tags)
        out = _TAG_RE.sub("", out)
    return {"text": out, "removed": sum(by_class.values()), "by_class": by_class}


def _scrub_image(data: bytes) -> tuple[bytes, list[str]]:
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.load()
    removed = [f"image metadata: {k}" for k in img.info.keys()] or ["no metadata found"]
    fmt = (img.format or "PNG").upper()
    if fmt in {"JPEG", "JPG"}:
        fmt = "JPEG"
    if img.mode == "P":
        img = img.convert("RGB")
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))
    buf = io.BytesIO()
    save_fmt = fmt if fmt in {"JPEG", "PNG", "WEBP", "GIF", "TIFF", "BMP"} else "PNG"
    clean.save(buf, format=save_fmt)  # no exif=/icc_profile=/info passed: nothing is written
    return buf.getvalue(), removed


_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_PROPS = {"docProps/core.xml", "docProps/app.xml", "docProps/custom.xml",
                 "docProps/thumbnail.jpeg", "docProps/thumbnail.png"}


def _scrub_office(data: bytes) -> tuple[bytes, list[str]]:
    src = zipfile.ZipFile(io.BytesIO(data))
    names = set(src.namelist())
    removed: list[str] = []
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            if name in _OFFICE_PROPS:
                removed.append(f"document properties: {name}")
                continue
            payload = src.read(name)
            if name == "_rels/.rels":
                ET.register_namespace("", _REL_NS)
                root = ET.fromstring(payload)
                for rel in list(root):
                    if rel.get("Target", "").replace("\\", "/").lstrip("/").startswith("docProps/"):
                        root.remove(rel)
                payload = ET.tostring(root, xml_declaration=True, encoding="UTF-8")
            elif name == "[Content_Types].xml":
                ET.register_namespace("", _CT_NS)
                root = ET.fromstring(payload)
                for ov in list(root):
                    if ov.get("PartName", "").startswith("/docProps/"):
                        root.remove(ov)
                payload = ET.tostring(root, xml_declaration=True, encoding="UTF-8")
            dst.writestr(name, payload)
    if not removed:
        removed = ["no document properties found"]
    if "word/document.xml" not in names and "xl/workbook.xml" not in names and "ppt/presentation.xml" not in names:
        raise filestore.FileStoreError("not a recognized Office document")
    return out.getvalue(), removed


def _scrub_pdf(data: bytes) -> tuple[bytes, list[str]]:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        raise filestore.FileStoreError("PDF scrubbing needs the optional pypdf package installed on this box")
    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    had_meta = bool(reader.metadata)
    out = io.BytesIO()
    writer.write(out)  # no metadata copied
    return out.getvalue(), (["PDF document info dictionary"] if had_meta else ["no PDF metadata found"])


_TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".xml", ".yaml", ".yml", ".log"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff", ".bmp"}
_OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}


def scrub_file(name: str) -> tuple[str, bytes, list[str]]:
    data = filestore.read_file(name)
    stem, dot, ext = name.rpartition(".")
    ext = ("." + ext.lower()) if dot else ""
    stem = stem or name
    if ext in _IMAGE_EXTS:
        cleaned, removed = _scrub_image(data)
    elif ext in _OFFICE_EXTS:
        cleaned, removed = _scrub_office(data)
    elif ext == ".pdf":
        cleaned, removed = _scrub_pdf(data)
    elif ext in _TEXT_EXTS or not ext:
        try:
            result = scrub_text(data.decode("utf-8"))
        except UnicodeDecodeError:
            raise filestore.FileStoreError("file is not UTF-8 text and not a supported image/Office/PDF type")
        cleaned = result["text"].encode()
        removed = [f"{k}: {v} invisible characters" for k, v in result["by_class"].items()] or ["no invisible characters found"]
    else:
        raise filestore.FileStoreError(f"unsupported file type '{ext}' (images, Office docs, PDF, and text files supported)")
    return f"{stem}-clean{ext}", cleaned, removed


def scrub_handler(conversation_id: int):
    async def h(inp: ScrubInput):
        if not inp.text and not inp.file:
            return {"error": "provide text or a file name to scrub"}
        if inp.text and not inp.file:
            result = scrub_text(inp.text)
            return {"mode": "text", "removed": result["removed"], "by_class": result["by_class"],
                    "cleaned_text": result["text"]}
        try:
            new_name, cleaned, removed = scrub_file(inp.file)
            meta = filestore.write_file(new_name, cleaned)
        except filestore.FileStoreError as exc:
            return {"error": str(exc)}
        from .delivery import deliver_file
        note = await deliver_file(conversation_id, meta["name"], cleaned,
                                  "application/octet-stream", caption=meta["name"])
        return {"mode": "file", "source": inp.file, "removed": removed,
                "created": True, "download": f"/files/{meta['name']}", **(note or {}), **meta}
    return h
