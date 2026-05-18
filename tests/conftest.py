"""Shared test fixtures.

Single session-scoped TestClient for HTTP tests (the
StreamableHTTPSessionManager hard-errors on `run()` being called twice).

A few tiny PDFs are generated on the fly via pypdf so the test suite
doesn't carry binary fixtures.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter


@pytest.fixture(scope="session", autouse=True)
def _isolate_output_root(tmp_path_factory) -> None:
    """Point OUTPUT_ROOT and CACHE_ROOT at temp dirs for the whole session."""
    out = tmp_path_factory.mktemp("output")
    cache = tmp_path_factory.mktemp("cache")
    os.environ["OUTPUT_ROOT"] = str(out)
    os.environ["CACHE_ROOT"] = str(cache)
    # Importing config picks these up; reload to be safe if it was already
    # imported by a previous test module.
    import importlib

    from flint_slating import config

    importlib.reload(config)


@pytest.fixture(scope="session")
def mcp_client() -> TestClient:
    from flint_slating.app import app

    with TestClient(app) as c:
        yield c


def _make_blank_pdf(n_pages: int, *, with_metadata: bool = True) -> bytes:
    """Build an in-memory PDF with `n_pages` blank pages (612x792 = US Letter)."""
    writer = PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=612, height=792)
    if with_metadata:
        writer.add_metadata(
            {
                "/Title": "Test PDF",
                "/Author": "flint-slating tests",
                "/Subject": "fixture",
            }
        )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        writer.write(f)
        path = Path(f.name)
    data = path.read_bytes()
    path.unlink()
    return data


@pytest.fixture
def tiny_pdf_bytes() -> bytes:
    return _make_blank_pdf(2)


@pytest.fixture
def tiny_pdf_path(tmp_path: Path, tiny_pdf_bytes: bytes) -> Path:
    p = tmp_path / "tiny.pdf"
    p.write_bytes(tiny_pdf_bytes)
    return p


@pytest.fixture
def encrypted_pdf_path(tmp_path: Path) -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt(user_password="hunter2", owner_password=None)
    p = tmp_path / "locked.pdf"
    with open(p, "wb") as f:
        writer.write(f)
    return p
