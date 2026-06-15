# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Pydantic models shared between MCP tool dispatch and HTTP routes.

Kept narrow: only what's actually exchanged at the public boundary.
Internal data passes around as plain dicts/dataclasses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PdfSource(BaseModel):
    """Exactly one of `path`, `url`, or `bytes_b64` must be set."""

    path: str | None = Field(
        default=None,
        description="Absolute local filesystem path to a PDF.",
    )
    url: str | None = Field(
        default=None,
        description="http(s) URL to a PDF. Will be streamed to CACHE_ROOT.",
    )
    bytes_b64: str | None = Field(
        default=None,
        description="Base64-encoded PDF bytes. Size-capped via MAX_INLINE_PDF_BYTES.",
    )
    filename: str | None = Field(
        default=None,
        description="Optional filename hint used when materializing base64 input.",
    )


class JobRef(BaseModel):
    job_id: str
    state: Literal["pending", "running", "done", "failed", "cancelled"]
    progress: float = 0.0
    output_url: str | None = None
    error: str | None = None
