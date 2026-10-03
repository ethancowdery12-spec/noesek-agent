"""Document ingest: turn inbound documents into Markdown the agent can read.

Ethan's roadmap P2 (Sep 20 2026): docling (docling-project/docling, MIT)
and markitdown (microsoft/markitdown, MIT) make documents AI-ready. Design:

- markitdown is the built-in engine: light, pure-Python deps, covers
  PDF/DOCX/PPTX/XLSX/HTML/images(metadata)/CSV/JSON.
- docling is the optional heavy engine for complex layouts (tables,
  formulas, scanned pages): `pip install noesek-agent[docling]`. Used for
  PDFs when installed and NOESEK_DOC_ENGINE=auto (default) or docling.
- Text-like inputs (plain/markdown/csv/json) pass through with no engine.

Converted output is UNTRUSTED content: callers wrap it with
core.content_guard.guard_untrusted before it enters model context (a PDF
can carry injection text just like a web page).
"""
from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass, field

MAX_DOC_BYTES = 10_000_000
MAX_MARKDOWN_CHARS = 20_000

_TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".yaml", ".yml", ".xml"}
_TEXT_MIMES = {"text/plain", "text/markdown", "text/csv", "application/json"}


@dataclass
class DocResult:
    ok: bool
    markdown: str = ""
    engine: str = "none"
    error: str = ""
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


def _ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def _is_text_like(filename: str, mime: str) -> bool:
    return _ext(filename) in _TEXT_EXTS or (mime or "").split(";")[0].strip() in _TEXT_MIMES


def _engine_choice(filename: str) -> str:
    want = os.environ.get("NOESEK_DOC_ENGINE", "auto").strip().lower()
    if want == "markitdown":
        return "markitdown"
    if want in ("auto", "docling") and _ext(filename) == ".pdf":
        try:
            import docling  # noqa: F401
            return "docling"
        except ImportError:
            if want == "docling":
                return "docling-missing"
    return "markitdown"


def _convert_docling(data: bytes, filename: str) -> str:
    from docling.document_converter import DocumentConverter
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=_ext(filename) or ".pdf", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        result = DocumentConverter().convert(path)
        return result.document.export_to_markdown()
    finally:
        os.unlink(path)


def _convert_markitdown(data: bytes, filename: str) -> str:
    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert_stream(io.BytesIO(data), file_extension=_ext(filename) or None)
    return result.text_content or ""


def convert_to_markdown(data: bytes, filename: str = "", mime: str = "", *, local_ocr=None) -> DocResult:
    """Convert one document's bytes to Markdown. Never raises on bad input."""
    if not data:
        return DocResult(ok=False, error="empty document")
    if len(data) > MAX_DOC_BYTES:
        return DocResult(ok=False, error=f"document too large ({len(data)} bytes > {MAX_DOC_BYTES})")
    if zipfile.is_zipfile(io.BytesIO(data)):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members=archive.infolist()
                if len(members)>2000 or sum(i.file_size for i in members)>MAX_DOC_BYTES or any(i.file_size>MAX_DOC_BYTES for i in members):
                    return DocResult(ok=False,error='expanded document exceeds limits')
                # Read bounded members to validate claimed expansion/CRC before conversion.
                expanded=0
                for member in members:
                    with archive.open(member) as stream:
                        while chunk:=stream.read(65536):
                            expanded+=len(chunk)
                            if expanded>MAX_DOC_BYTES:return DocResult(ok=False,error='expanded document exceeds limits')
        except Exception as exc:return DocResult(ok=False,error=f'invalid document archive: {type(exc).__name__}')
    if _is_text_like(filename, mime):
        try: text=data.decode('utf-8',errors='strict')
        except UnicodeError:return DocResult(ok=False,engine='passthrough',error='text is not valid UTF-8')
        return _finish(text,'passthrough')
    if local_ocr is not None and _ext(filename) in {".png", ".jpg", ".jpeg", ".webp"}:
        try:return local_ocr.read(data, filename)
        except Exception as exc:return DocResult(ok=False,engine='unlimited-ocr',error=f'adapter failed: {type(exc).__name__}')
    if local_ocr is not None and _ext(filename)=='.pdf' and hasattr(local_ocr,'read_pdf'):
        # Scanned PDFs have no text layer: try the normal engine first, OCR only when it finds nothing.
        first=_convert_pdf_text(data,filename)
        if first is not None:return first
        try:return local_ocr.read_pdf(data,filename)
        except Exception as exc:return DocResult(ok=False,engine='unlimited-ocr-pdf',error=f'adapter failed: {type(exc).__name__}')
    engine = _engine_choice(filename)
    if engine == "docling-missing":
        return DocResult(ok=False, engine="docling", error="docling requested but not installed (pip install noesek-agent[docling])")
    try:
        if engine == "docling":
            try:
                text = _convert_docling(data, filename)
            except Exception as e:
                # fall back to markitdown rather than failing the user
                text = _convert_markitdown(data, filename)
                engine = "markitdown"
                fallback = f"docling failed ({type(e).__name__}); used markitdown"
                return _finish(text, engine, fallback)
        else:
            text = _convert_markitdown(data, filename)
        return _finish(text, engine)
    except Exception as e:
        return DocResult(ok=False, engine=engine, error=f"conversion failed: {type(e).__name__}: {str(e)[:200]}")


def _convert_pdf_text(data: bytes, filename: str):
    """Text-layer PDF result, or None when the PDF has no readable text (scanned) so OCR can run."""
    try:text=_convert_markitdown(data,filename)
    except Exception:return None
    if len((text or '').strip())<20:return None
    return _finish(text,'markitdown')


def _finish(text: str, engine: str, warning: str | None = None) -> DocResult:
    text = (text or "").strip()
    if not text:
        return DocResult(ok=False, engine=engine, error="no readable text extracted")
    warnings = [warning] if warning else []
    return DocResult(ok=True, markdown=text[:MAX_MARKDOWN_CHARS], engine=engine,
                     truncated=len(text) > MAX_MARKDOWN_CHARS, warnings=warnings)
