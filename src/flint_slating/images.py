"""Image listing and extraction.

Backed by pypdf — Docling's image objects don't carry the raw stream
bytes in a stable way across versions, but pypdf gives us direct xref
access. Permissive license (BSD-3), already in the dep tree.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from flint_slating import config
from flint_slating.pdf_reader import EncryptedPdfError, PdfError, _open_pypdf


def list_images(path: Path, password: str | None = None) -> dict[str, Any]:
    """Return a flat list of image stubs across the document.

    Each entry: `{page, index, name, width, height, ext}`. The (page,
    index) pair is enough to extract the bytes via `extract_image`.
    """
    reader = _open_pypdf(path, password)
    if reader.is_encrypted:
        raise EncryptedPdfError("PDF is encrypted; provide a password")
    out: list[dict[str, Any]] = []
    for pno, page in enumerate(reader.pages, start=1):
        try:
            images = page.images  # pypdf returns a list of ImageFile
        except Exception as e:
            raise PdfError(f"image enumeration failed on page {pno}: {e}") from e
        for idx, img in enumerate(images):
            out.append(
                {
                    "page": pno,
                    "index": idx,
                    "name": getattr(img, "name", "") or "",
                    "width": _img_dim(img, "width"),
                    "height": _img_dim(img, "height"),
                    "ext": _ext_from_name(getattr(img, "name", "") or ""),
                }
            )
    return {"images": out}


def extract_image(
    path: Path,
    *,
    page: int,
    index: int,
    password: str | None = None,
) -> dict[str, Any]:
    """Extract one image's raw bytes by (1-based page, 0-based index).

    Returns base64-encoded data and the original extension. Capped by
    `config.MAX_IMAGE_EXTRACT_BYTES`.
    """
    reader = _open_pypdf(path, password)
    if reader.is_encrypted:
        raise EncryptedPdfError("PDF is encrypted; provide a password")
    if page < 1 or page > len(reader.pages):
        raise PdfError(f"page {page} out of range (1..{len(reader.pages)})")
    images = reader.pages[page - 1].images
    if index < 0 or index >= len(images):
        raise PdfError(f"image index {index} out of range (0..{len(images) - 1})")
    img = images[index]
    raw = bytes(img.data or b"")
    if len(raw) == 0:
        raise PdfError("image has no data")
    if len(raw) > config.MAX_IMAGE_EXTRACT_BYTES:
        raise PdfError(
            f"image size {len(raw)} exceeds MAX_IMAGE_EXTRACT_BYTES "
            f"({config.MAX_IMAGE_EXTRACT_BYTES})"
        )
    return {
        "page": page,
        "index": index,
        "ext": _ext_from_name(getattr(img, "name", "") or ""),
        "size": len(raw),
        "data_b64": base64.b64encode(raw).decode("ascii"),
    }


def _img_dim(img: Any, attr: str) -> int | None:
    try:
        pil = getattr(img, "image", None)
        if pil is not None:
            return int(getattr(pil, attr.replace("width", "width").replace("height", "height")))
    except Exception:
        pass
    return None


def _ext_from_name(name: str) -> str:
    name = name.lower()
    for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"):
        if name.endswith(ext):
            return ext.lstrip(".")
    return ""
