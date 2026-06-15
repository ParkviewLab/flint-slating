# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Job table behavior (no Docling — we monkeypatch the read step)."""

from __future__ import annotations

import time

import pytest

from flint_slating import jobs, outputs, pdf_reader, pdf_source


@pytest.fixture
def resolved_tiny(tiny_pdf_path):
    return pdf_source.resolve({"path": str(tiny_pdf_path)})


def test_start_and_complete_read_markdown(resolved_tiny, monkeypatch):
    monkeypatch.setattr(
        pdf_reader,
        "read_markdown",
        lambda path, **kw: {"markdown": "# fake\n", "page_count": 2},
    )
    job_id, job_dir = jobs.start_read_markdown(resolved=resolved_tiny, pages=None, password=None)

    snap = jobs.wait_for_result(job_id, timeout_seconds=10)
    assert snap["state"] == "done"
    assert outputs.read_result_markdown(job_dir).startswith("# fake")


def test_start_and_complete_read_chunks(resolved_tiny, monkeypatch):
    fake = {"page_count": 1, "chunks": [{"page_number": 1, "markdown": "x"}]}
    monkeypatch.setattr(pdf_reader, "read_chunks", lambda path, **kw: fake)
    job_id, job_dir = jobs.start_read_chunks(resolved=resolved_tiny, pages=None, password=None)
    snap = jobs.wait_for_result(job_id, timeout_seconds=10)
    assert snap["state"] == "done"
    assert "chunks" in outputs.read_result_json(job_dir)


def test_cancel_then_get(resolved_tiny, monkeypatch):
    def _slow(path, **kw):
        time.sleep(0.5)
        return {"markdown": "", "page_count": 0}

    monkeypatch.setattr(pdf_reader, "read_markdown", _slow)
    job_id, _ = jobs.start_read_markdown(resolved=resolved_tiny, pages=None, password=None)
    assert jobs.cancel(job_id) is True
    # cancel is cooperative — the job is allowed to finish; we just verify
    # the call doesn't blow up and the eventual state is terminal.
    snap = jobs.wait_for_result(job_id, timeout_seconds=10)
    assert snap["state"] in {"done", "cancelled", "failed"}


def test_failure_records_error(resolved_tiny, monkeypatch):
    def _boom(path, **kw):
        raise RuntimeError("nope")

    monkeypatch.setattr(pdf_reader, "read_markdown", _boom)
    job_id, _ = jobs.start_read_markdown(resolved=resolved_tiny, pages=None, password=None)
    snap = jobs.wait_for_result(job_id, timeout_seconds=5)
    assert snap["state"] == "failed"
    assert "nope" in (snap["error"] or "")
