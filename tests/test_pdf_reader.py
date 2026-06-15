# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Coverage for the pypdf-backed reader functions.

Docling-backed paths are tested separately (`-m docling`) because they
download a layout model on first run.
"""

from __future__ import annotations

import pytest

from flint_slating import pdf_reader


def test_info_returns_page_count(tiny_pdf_path):
    out = pdf_reader.info(tiny_pdf_path)
    assert out["page_count"] == 2
    assert out["is_encrypted"] is False
    assert out["metadata"]["title"] == "Test PDF"


def test_info_on_encrypted_marks_encrypted(encrypted_pdf_path):
    out = pdf_reader.info(encrypted_pdf_path)
    assert out["is_encrypted"] is True


def test_read_text_returns_one_record_per_page(tiny_pdf_path):
    out = pdf_reader.read_text(tiny_pdf_path)
    assert out["page_count"] == 2
    assert len(out["pages"]) == 2
    assert out["pages"][0]["page"] == 1


def test_read_text_pages_filter(tiny_pdf_path):
    out = pdf_reader.read_text(tiny_pdf_path, pages=[2])
    assert len(out["pages"]) == 1
    assert out["pages"][0]["page"] == 2


def test_toc_empty_when_no_outline(tiny_pdf_path):
    assert pdf_reader.toc(tiny_pdf_path) == []


def test_encrypted_pdf_raises_without_password(encrypted_pdf_path):
    # read_text on an encrypted PDF without password — pypdf raises a
    # FileNotDecryptedError when we touch reader.pages. Allow either that
    # or our own PdfError if a future revision wraps it.
    from pypdf.errors import FileNotDecryptedError

    with pytest.raises((FileNotDecryptedError, pdf_reader.PdfError)):
        pdf_reader.read_text(encrypted_pdf_path)


def test_encrypted_pdf_unlocks_with_password(encrypted_pdf_path):
    out = pdf_reader.info(encrypted_pdf_path, password="hunter2")
    assert out["is_encrypted"] is True  # the flag stays set; the reader is now decrypted
    assert out["page_count"] == 1
