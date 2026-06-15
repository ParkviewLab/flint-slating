# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""pdf_source.resolve covers all three input shapes."""

from __future__ import annotations

import base64

import pytest

from flint_slating import pdf_source


def test_resolve_path(tiny_pdf_path):
    r = pdf_source.resolve({"path": str(tiny_pdf_path)})
    assert r.path == tiny_pdf_path
    assert r.is_cached is False
    assert r.size > 0
    assert len(r.sha256) == 64


def test_resolve_bytes_b64(tiny_pdf_bytes):
    b64 = base64.b64encode(tiny_pdf_bytes).decode("ascii")
    r = pdf_source.resolve({"bytes_b64": b64})
    assert r.path.exists()
    assert r.is_cached is True
    assert r.size == len(tiny_pdf_bytes)


def test_resolve_bytes_caches_by_hash(tiny_pdf_bytes):
    b64 = base64.b64encode(tiny_pdf_bytes).decode("ascii")
    r1 = pdf_source.resolve({"bytes_b64": b64})
    r2 = pdf_source.resolve({"bytes_b64": b64})
    assert r1.path == r2.path
    assert r1.sha256 == r2.sha256


def test_resolve_rejects_zero_keys():
    with pytest.raises(pdf_source.SourceError):
        pdf_source.resolve({})


def test_resolve_rejects_multiple_keys(tiny_pdf_path):
    with pytest.raises(pdf_source.SourceError):
        pdf_source.resolve({"path": str(tiny_pdf_path), "url": "http://x/y.pdf"})


def test_resolve_rejects_non_pdf_bytes():
    b64 = base64.b64encode(b"hello world").decode("ascii")
    with pytest.raises(pdf_source.SourceError, match="PDF"):
        pdf_source.resolve({"bytes_b64": b64})


def test_resolve_rejects_missing_path(tmp_path):
    with pytest.raises(pdf_source.SourceError, match="not found"):
        pdf_source.resolve({"path": str(tmp_path / "missing.pdf")})
