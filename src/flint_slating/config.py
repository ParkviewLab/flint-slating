# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Static configuration. Pure leaf module — no internal imports."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    VERSION: str = version("flint-slating")
except PackageNotFoundError:
    VERSION = "0.0.0+local"

PORT = int(os.environ.get("PORT", "35833"))
HOST = os.environ.get("HOST", "0.0.0.0")

PUBLIC_BASE_URL: str = (os.environ.get("PUBLIC_BASE_URL") or f"http://localhost:{PORT}").rstrip("/")

OUTPUT_ROOT: Path = Path(os.environ.get("OUTPUT_ROOT", "./output")).resolve()
CACHE_ROOT: Path = Path(os.environ.get("CACHE_ROOT", "./cache")).resolve()

OUTPUT_EXPIRY_DAYS: int = int(os.environ.get("OUTPUT_EXPIRY_DAYS", "7"))
JOB_HISTORY_MAX: int = int(os.environ.get("JOB_HISTORY_MAX", "100"))

# Inline-source caps. Anything bigger than these gets refused at the
# pdf_source boundary — we never put a 1 GB base64 blob through the MCP
# transport.
MAX_INLINE_PDF_BYTES: int = int(os.environ.get("MAX_INLINE_PDF_BYTES", str(25 * 1024 * 1024)))
MAX_URL_PDF_BYTES: int = int(os.environ.get("MAX_URL_PDF_BYTES", str(200 * 1024 * 1024)))

# Page count under which Docling-backed tools run inline (sync) rather
# than queuing a job. OCR runs always queue, regardless of page count.
SYNC_PAGE_THRESHOLD: int = int(os.environ.get("SYNC_PAGE_THRESHOLD", "20"))

# Where Docling reads its models from, only when the operator sets it.
# Docling treats a set path as a directory that must already hold every
# model, and never downloads into it; left unset, Docling downloads the
# models on first use. So this is read, never exported with a default.
_docling_artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH")
DOCLING_ARTIFACTS_PATH: Path | None = Path(_docling_artifacts).resolve() if _docling_artifacts else None

ENABLE_OCR: bool = os.environ.get("ENABLE_OCR", "false").lower() in {"1", "true", "yes", "on"}

# Image extraction caps to keep response payloads sane.
MAX_IMAGE_EXTRACT_BYTES: int = int(os.environ.get("MAX_IMAGE_EXTRACT_BYTES", str(8 * 1024 * 1024)))
