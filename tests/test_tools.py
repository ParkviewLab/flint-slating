"""Tool dispatch — verify the JSON shapes the MCP transport will emit."""

from __future__ import annotations

import base64
import json

import pytest

from flint_slating import tools


def _text_payload(result):
    assert len(result) == 1
    item = result[0]
    assert item.type == "text"
    return json.loads(item.text)


@pytest.mark.asyncio
async def test_pdf_info_dispatch(tiny_pdf_path):
    out = _text_payload(await tools.dispatch("pdf_info", {"source": {"path": str(tiny_pdf_path)}}))
    assert out["page_count"] == 2
    assert "sha256" in out


@pytest.mark.asyncio
async def test_pdf_toc_dispatch(tiny_pdf_path):
    out = _text_payload(await tools.dispatch("pdf_toc", {"source": {"path": str(tiny_pdf_path)}}))
    assert out["toc"] == []


@pytest.mark.asyncio
async def test_pdf_read_text_dispatch_via_bytes(tiny_pdf_bytes):
    b64 = base64.b64encode(tiny_pdf_bytes).decode("ascii")
    out = _text_payload(
        await tools.dispatch("pdf_read_text", {"source": {"bytes_b64": b64}, "pages": [1]})
    )
    assert out["page_count"] == 2
    assert len(out["pages"]) == 1


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    out = _text_payload(await tools.dispatch("nope", {"source": {"path": "x"}}))
    assert out["error"] == "unknown_tool"


@pytest.mark.asyncio
async def test_bad_source_returns_error():
    out = _text_payload(await tools.dispatch("pdf_info", {"source": {}}))
    assert out["error"] == "bad_source"


@pytest.mark.asyncio
async def test_cancel_unknown_job_is_false():
    out = _text_payload(await tools.dispatch("cancel_job", {"job_id": "nope"}))
    assert out["ok"] is False


@pytest.mark.asyncio
async def test_get_job_status_unknown():
    out = _text_payload(await tools.dispatch("get_job_status", {"job_id": "nope"}))
    assert out["error"] == "unknown_job_id"
