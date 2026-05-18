"""PDF reading primitives — pypdf for fast structural ops, Docling for
high-quality Markdown.

Tool-facing functions return plain dicts (JSON-serializable) so the MCP
dispatcher can hand them straight to `TextContent`.

Docling is imported lazily — it pulls heavy ML deps, and we don't want
`pdf_info` or `pdf_toc` calls to pay that cost. `warm_docling()` exists
so the entry point can pay it once at startup, off the request path.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

log = logging.getLogger(__name__)

# Module-level cache for the heavy DocumentConverter so we build it once.
_docling_lock = threading.Lock()
_docling_converter: Any = None


class PdfError(Exception):
    """Raised by reader functions when a PDF can't be read.

    The string form is safe to surface to the user.
    """


class EncryptedPdfError(PdfError):
    """The PDF is encrypted and no working password was provided."""


# ---------------------------------------------------------------------------
# pypdf-backed reads (cheap / sync)


def info(path: Path, password: str | None = None) -> dict[str, Any]:
    """Return basic metadata: page count, doc metadata, encryption status.

    Tolerant of locked PDFs: when `password` is None and the PDF is
    encrypted, returns `{is_encrypted: True}` with empty metadata and
    `page_count=None` rather than raising — agents need this signal to
    know whether to ask the user for a password.
    """
    reader = _open_pypdf(path, password)
    locked = reader.is_encrypted and not _is_decrypted(reader)
    if locked:
        return {
            "path": str(path),
            "page_count": None,
            "is_encrypted": True,
            "metadata": {},
        }
    meta = reader.metadata or {}
    return {
        "path": str(path),
        "page_count": len(reader.pages),
        "is_encrypted": reader.is_encrypted,
        "metadata": {
            "title": _coerce_str(meta.get("/Title")),
            "author": _coerce_str(meta.get("/Author")),
            "subject": _coerce_str(meta.get("/Subject")),
            "creator": _coerce_str(meta.get("/Creator")),
            "producer": _coerce_str(meta.get("/Producer")),
            "creation_date": _coerce_str(meta.get("/CreationDate")),
            "mod_date": _coerce_str(meta.get("/ModDate")),
            "keywords": _coerce_str(meta.get("/Keywords")),
        },
    }


def _is_decrypted(reader: PdfReader) -> bool:
    """Whether `reader.decrypt()` has been called successfully.

    pypdf doesn't expose this directly, so we probe the private
    `_encryption` attribute. Falls back to True (unlocked) when the
    attribute is missing — better to attempt the read than to refuse.
    """
    enc = getattr(reader, "_encryption", None)
    if enc is None:
        return True
    try:
        return bool(enc.is_decrypted())
    except Exception:
        return False


def toc(path: Path, password: str | None = None) -> list[dict[str, Any]]:
    """Flat list of outline items: `[{level, title, page}]`.

    Empty list when the PDF has no outline.
    """
    reader = _open_pypdf(path, password)
    flat: list[dict[str, Any]] = []
    try:
        outline = reader.outline
    except Exception as e:  # pypdf raises a variety of internal errors here
        log.debug("outline read failed: %s", e)
        return []
    _flatten_outline(reader, outline, level=1, into=flat)
    return flat


def read_text(
    path: Path,
    *,
    pages: list[int] | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Plain text extraction by page range — fast, no ML model."""
    reader = _open_pypdf(path, password)
    total = len(reader.pages)
    selected = _normalize_pages(pages, total)
    out: list[dict[str, Any]] = []
    for pno in selected:
        try:
            text = reader.pages[pno].extract_text() or ""
        except Exception as e:
            log.debug("text extract failed on page %d: %s", pno, e)
            text = ""
        out.append({"page": pno + 1, "text": text})
    return {"pages": out, "page_count": total}


# ---------------------------------------------------------------------------
# Docling-backed reads (high-quality Markdown)


def warm_docling() -> None:
    """Build the DocumentConverter once so the first user-facing call is hot.

    Safe to call before / instead of the first conversion. The model
    download (if any) happens here. Idempotent and thread-safe.
    """
    _get_converter()


def read_markdown(
    path: Path,
    *,
    pages: list[int] | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Convert a PDF (or page subset) to a single Markdown string."""
    if password:
        _verify_unlockable(path, password)
    converter = _get_converter()
    page_range = _docling_page_range(pages)
    try:
        if page_range is None:
            result = converter.convert(str(path))
        else:
            result = converter.convert(str(path), page_range=page_range)
    except Exception as e:
        raise PdfError(f"docling conversion failed: {e}") from e
    document = result.document
    return {
        "markdown": document.export_to_markdown(),
        "page_count": _docling_page_count(document),
    }


def read_chunks(
    path: Path,
    *,
    pages: list[int] | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Per-page Markdown chunks.

    Returns:
        {
          "page_count": int,
          "chunks": [
            {"page_number": int, "markdown": str,
             "tables": [...], "images": [...], "toc_items": [...]},
            ...
          ]
        }
    """
    if password:
        _verify_unlockable(path, password)
    converter = _get_converter()
    page_range = _docling_page_range(pages)
    try:
        if page_range is None:
            result = converter.convert(str(path))
        else:
            result = converter.convert(str(path), page_range=page_range)
    except Exception as e:
        raise PdfError(f"docling conversion failed: {e}") from e
    document = result.document
    return {
        "page_count": _docling_page_count(document),
        "chunks": list(_per_page_chunks(document)),
    }


# ---------------------------------------------------------------------------
# Helpers


def _get_converter() -> Any:
    """Lazy, thread-safe DocumentConverter singleton."""
    global _docling_converter
    if _docling_converter is not None:
        return _docling_converter
    with _docling_lock:
        if _docling_converter is None:
            from docling.document_converter import DocumentConverter

            _docling_converter = DocumentConverter()
    return _docling_converter


def _docling_page_range(pages: list[int] | None) -> tuple[int, int] | None:
    """Docling takes a `(first, last)` 1-based inclusive range. Our public
    API uses 0-based page indices; convert.
    """
    if not pages:
        return None
    p1 = min(pages)
    p2 = max(pages)
    return (p1 + 1, p2 + 1)


def _docling_page_count(document: Any) -> int:
    # docling exposes pages via document.pages (a dict in current versions);
    # fall back to len(list(document.pages)) in case the attribute shape
    # changes in a minor release.
    pages = getattr(document, "pages", None)
    if pages is None:
        return 0
    try:
        return len(pages)
    except TypeError:
        return sum(1 for _ in pages)


def _per_page_chunks(document: Any) -> Iterable[dict[str, Any]]:
    """Yield one dict per page using docling's grouping by page number.

    The shape mirrors pymupdf4llm's `page_chunks=True` output so wiki-side
    prompts written against that library can be reused with minor field
    renames.
    """
    pages_attr = getattr(document, "pages", {}) or {}
    page_nos = sorted(pages_attr.keys()) if isinstance(pages_attr, dict) else range(
        1, _docling_page_count(document) + 1
    )
    for pno in page_nos:
        # Per-page markdown
        try:
            md = document.export_to_markdown(page_no=pno)
        except TypeError:
            # older docling: no page_no arg; export full and skip subset
            md = ""
        yield {
            "page_number": int(pno),
            "markdown": md,
            "tables": _page_tables(document, int(pno)),
            "images": _page_images(document, int(pno)),
            "toc_items": _page_toc_items(document, int(pno)),
        }


def _page_tables(document: Any, page_no: int) -> list[dict[str, Any]]:
    """Tables on a given page as `{markdown, bbox?}` records."""
    out: list[dict[str, Any]] = []
    for table in getattr(document, "tables", []) or []:
        if _table_page(table) != page_no:
            continue
        try:
            df = table.export_to_dataframe()
            md = df.to_markdown(index=False) if df is not None else ""
        except Exception:
            md = ""
        out.append({"markdown": md, "bbox": _safe_bbox(table)})
    return out


def _page_images(document: Any, page_no: int) -> list[dict[str, Any]]:
    """Image stubs (no bytes here — use `extract_image` for that)."""
    out: list[dict[str, Any]] = []
    for picture in getattr(document, "pictures", []) or []:
        if _table_page(picture) != page_no:
            continue
        out.append({"bbox": _safe_bbox(picture)})
    return out


def _page_toc_items(document: Any, page_no: int) -> list[dict[str, Any]]:
    """Outline items pointing at this page, in the LlamaIndex/pymupdf4llm shape."""
    items: list[dict[str, Any]] = []
    # docling exposes section headers via .texts with label == "section_header".
    for text in getattr(document, "texts", []) or []:
        if getattr(text, "label", None) != "section_header":
            continue
        if _table_page(text) != page_no:
            continue
        items.append(
            {
                "level": getattr(text, "level", 1) or 1,
                "title": getattr(text, "text", "") or "",
                "page": page_no,
            }
        )
    return items


def _table_page(item: Any) -> int | None:
    """Best-effort 1-based page-number extraction from a docling item."""
    prov = getattr(item, "prov", None)
    if not prov:
        return None
    try:
        first = prov[0]
        return int(getattr(first, "page_no", getattr(first, "page", 0)) or 0) or None
    except (IndexError, TypeError, ValueError):
        return None


def _safe_bbox(item: Any) -> list[float] | None:
    prov = getattr(item, "prov", None)
    if not prov:
        return None
    try:
        bbox = prov[0].bbox
        return [float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)]
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


def _open_pypdf(path: Path, password: str | None) -> PdfReader:
    """Open with pypdf and authenticate if needed."""
    try:
        reader = PdfReader(str(path))
    except PdfReadError as e:
        raise PdfError(f"could not read PDF: {e}") from e
    except PyPdfError as e:
        raise PdfError(f"could not read PDF: {e}") from e
    if reader.is_encrypted:
        if password is None:
            # info() needs to report encryption status without erroring,
            # so we don't raise here — but the caller can choose to.
            # Most read tools call _open_pypdf via a thin wrapper that
            # raises EncryptedPdfError once they've inspected reader.is_encrypted.
            return reader
        try:
            ok = reader.decrypt(password)
        except Exception as e:
            raise PdfError(f"decrypt failed: {e}") from e
        if not ok:
            raise EncryptedPdfError("password did not unlock the PDF")
    return reader


def _verify_unlockable(path: Path, password: str) -> None:
    reader = _open_pypdf(path, password)
    if reader.is_encrypted:
        # _open_pypdf only returns an encrypted reader when password was None,
        # so reaching here means decrypt() succeeded; nothing more to do.
        pass


def _flatten_outline(
    reader: PdfReader,
    items: Any,
    *,
    level: int,
    into: list[dict[str, Any]],
) -> None:
    if not items:
        return
    for item in items:
        if isinstance(item, list):
            _flatten_outline(reader, item, level=level + 1, into=into)
            continue
        title = ""
        page_no: int | None = None
        try:
            title = str(getattr(item, "title", "") or "")
            dest = item
            page_index = reader.get_destination_page_number(dest)
            page_no = (int(page_index) + 1) if page_index is not None else None
        except Exception as e:  # pypdf raises various things here
            log.debug("outline item resolve failed: %s", e)
        if title:
            into.append({"level": level, "title": title, "page": page_no})


def _coerce_str(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return str(v)
    except Exception:
        return None


def _normalize_pages(pages: list[int] | None, total: int) -> list[int]:
    """Convert a 1-based user page list into 0-based bounded indices. None = all."""
    if not pages:
        return list(range(total))
    out: list[int] = []
    seen: set[int] = set()
    for p in pages:
        idx = int(p) - 1
        if 0 <= idx < total and idx not in seen:
            seen.add(idx)
            out.append(idx)
    return out
