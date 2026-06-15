# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Resolve a `PdfSource` (path | url | base64) to a local file on disk.

Every MCP tool that takes a PDF calls `resolve(arguments)` first and
operates on the returned `Path`. URL and base64 inputs are materialized
under `config.CACHE_ROOT`, keyed by content hash so identical PDFs share
a single cached copy across calls.

Size caps live here too — refuse huge downloads / uploads before any
parser is asked to look at them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from flint_slating import config

log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"


class SourceError(Exception):
    """A PdfSource was malformed or rejected (size, MIME, missing file)."""


@dataclass(frozen=True)
class Resolved:
    path: Path
    # True when we materialized the file under CACHE_ROOT (URL / base64).
    # False when the user passed a path we just validated in place.
    is_cached: bool
    sha256: str
    size: int


def resolve(source: dict[str, Any]) -> Resolved:
    """Resolve a tool-call `source` dict to a local PDF on disk.

    Accepts the same shape as `schema.PdfSource`:
        {"path": "..."} | {"url": "..."} | {"bytes_b64": "...", "filename": "..."}

    Raises `SourceError` on any user-facing problem (missing, oversize,
    bad base64, non-PDF, etc.).
    """
    set_keys = [k for k in ("path", "url", "bytes_b64") if source.get(k)]
    if len(set_keys) == 0:
        raise SourceError("source must set exactly one of path | url | bytes_b64")
    if len(set_keys) > 1:
        raise SourceError(f"source must set exactly one of path | url | bytes_b64 (got {set_keys})")

    if "path" in set_keys:
        return _resolve_path(source["path"])
    if "url" in set_keys:
        return _resolve_url(source["url"])
    return _resolve_bytes(source["bytes_b64"], source.get("filename") or "")


def _resolve_path(raw_path: str) -> Resolved:
    p = Path(raw_path).expanduser()
    if not p.is_absolute():
        p = p.resolve()
    if not p.exists():
        raise SourceError(f"path not found: {raw_path}")
    if not p.is_file():
        raise SourceError(f"path is not a regular file: {raw_path}")
    size = p.stat().st_size
    if size == 0:
        raise SourceError("file is empty")
    _check_magic(p)
    digest = _sha256_file(p)
    return Resolved(path=p, is_cached=False, sha256=digest, size=size)


def _resolve_url(url: str) -> Resolved:
    if not (url.startswith("http://") or url.startswith("https://")):
        raise SourceError(f"unsupported URL scheme: {url!r}")
    _ensure_cache_dir()
    # Stream to a temp file, hash as we go, then rename to the
    # content-addressed final path so repeat fetches no-op.
    tmp = config.CACHE_ROOT / f".dl-{os.getpid()}-{os.urandom(4).hex()}.tmp"
    hasher = hashlib.sha256()
    size = 0
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as resp:
            if resp.status_code >= 400:
                raise SourceError(f"GET {url} returned HTTP {resp.status_code}")
            ctype = (resp.headers.get("content-type") or "").lower()
            # Tolerate octet-stream and missing types; reject only obvious
            # non-PDFs like text/html (common for "404 page" responses
            # that lie about being 200).
            if (
                ctype
                and "pdf" not in ctype
                and "octet-stream" not in ctype
                and any(bad in ctype for bad in ("html", "json", "xml"))
            ):
                raise SourceError(f"URL returned non-PDF content-type: {ctype}")
            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                    size += len(chunk)
                    if size > config.MAX_URL_PDF_BYTES:
                        raise SourceError(f"URL body exceeds MAX_URL_PDF_BYTES ({config.MAX_URL_PDF_BYTES})")
                    hasher.update(chunk)
                    f.write(chunk)
    except httpx.HTTPError as e:
        _unlink(tmp)
        raise SourceError(f"download failed: {e}") from e
    except SourceError:
        _unlink(tmp)
        raise

    digest = hasher.hexdigest()
    final = config.CACHE_ROOT / f"url-{digest}.pdf"
    if not final.exists():
        os.replace(tmp, final)
    else:
        _unlink(tmp)
    _check_magic(final)
    return Resolved(path=final, is_cached=True, sha256=digest, size=final.stat().st_size)


def _resolve_bytes(b64: str, filename: str) -> Resolved:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise SourceError(f"bytes_b64 is not valid base64: {e}") from e
    if len(raw) == 0:
        raise SourceError("bytes_b64 decoded to zero bytes")
    if len(raw) > config.MAX_INLINE_PDF_BYTES:
        raise SourceError(
            f"bytes_b64 decoded size {len(raw)} exceeds MAX_INLINE_PDF_BYTES ({config.MAX_INLINE_PDF_BYTES})"
        )
    if not raw.startswith(PDF_MAGIC):
        raise SourceError("bytes_b64 does not look like a PDF (missing %PDF- magic)")
    _ensure_cache_dir()
    digest = hashlib.sha256(raw).hexdigest()
    final = config.CACHE_ROOT / f"b64-{digest}.pdf"
    if not final.exists():
        tmp = final.with_suffix(".pdf.tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, final)
    # `filename` is currently advisory only; we keep the parameter so the
    # MCP schema can echo it back without us inventing one.
    _ = filename
    return Resolved(path=final, is_cached=True, sha256=digest, size=len(raw))


def _check_magic(path: Path) -> None:
    with open(path, "rb") as f:
        head = f.read(5)
    if not head.startswith(PDF_MAGIC):
        raise SourceError(f"file does not look like a PDF (missing %PDF- magic): {path}")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_cache_dir() -> None:
    config.CACHE_ROOT.mkdir(parents=True, exist_ok=True)


def _unlink(p: Path) -> None:
    import contextlib

    with contextlib.suppress(OSError):
        p.unlink()
