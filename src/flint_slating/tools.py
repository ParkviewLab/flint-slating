# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Tool schemas + dispatch logic.

`TOOLS` is the static list returned by `@mcp.list_tools()`. `dispatch`
runs the actual work for a given tool name. Both are transport-agnostic
— they're called identically from the stdio path and the HTTP path.
"""

from __future__ import annotations

import json
from typing import Any

from mcp import types

from flint_slating import (
    config,
    images,
    jobs,
    outputs,
    pdf_reader,
    pdf_source,
    tables,
)

# ---------------------------------------------------------------------------
# Tool schemas


_SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "PDF source. Set EXACTLY one of `path`, `url`, or `bytes_b64`. "
        "Paths must be absolute and on the server's filesystem. URLs are "
        "streamed to a content-addressed cache. Base64 inputs are size-"
        "capped by MAX_INLINE_PDF_BYTES."
    ),
    "properties": {
        "path": {"type": "string"},
        "url": {"type": "string"},
        "bytes_b64": {"type": "string"},
        "filename": {"type": "string", "description": "Hint for base64 input."},
    },
}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> types.Tool:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"source": _SOURCE_SCHEMA, **properties},
        "required": ["source", *required],
    }
    return types.Tool(name=name, description=description, inputSchema=schema)


TOOLS: list[types.Tool] = [
    _tool(
        "pdf_info",
        (
            "Quick structural facts about a PDF: page_count, metadata "
            "(title/author/subject/dates/etc.), is_encrypted, sha256, "
            "size. Cheap — uses pypdf, never invokes Docling. Call this "
            "first to plan whether to use pdf_read_text (fast) or "
            "pdf_read_markdown (slower but high-quality)."
        ),
        {"password": {"type": "string", "description": "Optional decrypt password."}},
        [],
    ),
    _tool(
        "pdf_toc",
        (
            "Flat outline of the PDF: `[{level, title, page}]`. Empty list "
            "if no outline. Useful for navigating long documents — feed "
            "the page numbers back into pdf_read_text or pdf_read_markdown."
        ),
        {"password": {"type": "string"}},
        [],
    ),
    _tool(
        "pdf_read_text",
        (
            "Plain text by page range — fast (pypdf, no ML). Use for "
            "spot-checking content; for high-quality structured Markdown "
            "(headings, tables, multi-column reading order), use "
            "pdf_read_markdown instead."
        ),
        {
            "pages": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "description": "1-based page numbers. Omitted / empty = all pages.",
                "default": [],
            },
            "password": {"type": "string"},
        },
        [],
    ),
    _tool(
        "pdf_read_markdown",
        (
            "Convert the PDF to Markdown using Docling — heading hierarchy, "
            "multi-column reading order, Markdown tables, image placeholders. "
            "Small PDFs (page_count <= SYNC_PAGE_THRESHOLD, default 20) "
            "convert inline and return `{markdown, page_count}`. Larger PDFs "
            "queue a background job and return `{job_id, ...}` — poll "
            "get_job_status until state=='done', then fetch the result via "
            "get_job_result (or the output_url in HTTP mode)."
        ),
        {
            "pages": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "default": [],
            },
            "password": {"type": "string"},
        },
        [],
    ),
    _tool(
        "pdf_read_chunks",
        (
            "Per-page Markdown chunks with tables/images/toc_items per page. "
            "Shape: `[{page_number, markdown, tables, images, toc_items}]`. "
            "Same sync/async behavior as pdf_read_markdown."
        ),
        {
            "pages": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "default": [],
            },
            "password": {"type": "string"},
        },
        [],
    ),
    _tool(
        "pdf_list_images",
        (
            "Enumerate images in a PDF. Returns `{images: [{page, index, "
            "name, width, height, ext}]}`. Use the (page, index) pair with "
            "pdf_extract_image to fetch the bytes."
        ),
        {"password": {"type": "string"}},
        [],
    ),
    _tool(
        "pdf_extract_image",
        (
            "Pull one image's bytes by (page, index) — output is base64-"
            "encoded. Capped by MAX_IMAGE_EXTRACT_BYTES."
        ),
        {
            "page": {"type": "integer", "minimum": 1},
            "index": {"type": "integer", "minimum": 0},
            "password": {"type": "string"},
        },
        ["page", "index"],
    ),
    _tool(
        "pdf_find_tables",
        (
            "Per-page tables extracted via pdfplumber, rendered as Markdown. "
            "Returns `{tables: [{page, index, markdown, n_rows, n_cols}]}`."
        ),
        {
            "pages": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "default": [],
            },
            "password": {"type": "string"},
        },
        [],
    ),
    types.Tool(
        name="get_job_status",
        description=(
            "Poll a background job. Returns `{job_id, kind, state, "
            "output_url?, started_at, finished_at, error}`. State is one "
            "of pending|running|done|failed|cancelled. In stdio mode "
            "output_url is null — the result is delivered inline by the "
            "originating tool."
        ),
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),
    types.Tool(
        name="get_job_result",
        description=(
            "Read a finished job's artifact (Markdown for read_markdown, "
            "JSON for read_chunks). Errors with `artifact_missing` if the "
            "job hasn't finished or never produced output."
        ),
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),
    types.Tool(
        name="cancel_job",
        description="Cooperatively cancel a running job. Returns `{ok: bool}`.",
        inputSchema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Dispatch


def _ok(payload: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload))]


def _err(code: str, detail: str) -> list[types.TextContent]:
    return _ok({"error": code, "detail": detail})


def _resolve_or_err(arguments: dict[str, Any]) -> tuple[pdf_source.Resolved | None, Any]:
    source_arg = arguments.get("source") or {}
    if not isinstance(source_arg, dict):
        return None, _err("bad_source", "`source` must be an object")
    try:
        return pdf_source.resolve(source_arg), None
    except pdf_source.SourceError as e:
        return None, _err("bad_source", str(e))


async def dispatch(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    try:
        return await _dispatch(name, arguments)
    except pdf_reader.EncryptedPdfError as e:
        return _err("encrypted", str(e))
    except pdf_reader.PdfError as e:
        return _err("pdf_error", str(e))
    except outputs.ArtifactMissing as e:
        return _err("artifact_missing", str(e))
    except outputs.OutputError as e:
        return _err("bad_request", str(e))


async def _dispatch(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name in {
        "pdf_info",
        "pdf_toc",
        "pdf_read_text",
        "pdf_read_markdown",
        "pdf_read_chunks",
        "pdf_list_images",
        "pdf_extract_image",
        "pdf_find_tables",
    }:
        resolved, err = _resolve_or_err(arguments)
        if err is not None:
            return err
        assert resolved is not None
        password = arguments.get("password") or None
        pages = arguments.get("pages") or None

        if name == "pdf_info":
            return _ok(pdf_reader.info(resolved.path, password=password) | {"sha256": resolved.sha256})
        if name == "pdf_toc":
            return _ok({"toc": pdf_reader.toc(resolved.path, password=password)})
        if name == "pdf_read_text":
            return _ok(pdf_reader.read_text(resolved.path, pages=pages, password=password))
        if name == "pdf_list_images":
            return _ok(images.list_images(resolved.path, password=password))
        if name == "pdf_extract_image":
            return _ok(
                images.extract_image(
                    resolved.path,
                    page=int(arguments["page"]),
                    index=int(arguments["index"]),
                    password=password,
                )
            )
        if name == "pdf_find_tables":
            return _ok(tables.find_tables(resolved.path, pages=pages, password=password))
        if name == "pdf_read_markdown":
            return await _maybe_markdown_inline_or_job(
                resolved=resolved, pages=pages, password=password, kind="read_markdown"
            )
        if name == "pdf_read_chunks":
            return await _maybe_markdown_inline_or_job(
                resolved=resolved, pages=pages, password=password, kind="read_chunks"
            )

    if name == "get_job_status":
        snap = jobs.get_status(arguments["job_id"])
        if snap is None:
            return _err("unknown_job_id", arguments["job_id"])
        return _ok(snap)

    if name == "get_job_result":
        job_id = arguments["job_id"]
        snap = jobs.get_status(job_id)
        if snap is None:
            return _err("unknown_job_id", job_id)
        if snap["state"] != "done":
            return _err("not_done", f"job state={snap['state']}")
        job_dir = outputs.resolve_job_dir(job_id)
        if job_dir is None:
            return _err("artifact_missing", "job dir missing")
        if snap["kind"] == "read_markdown":
            return _ok({"markdown": outputs.read_result_markdown(job_dir)})
        return _ok(json.loads(outputs.read_result_json(job_dir)))

    if name == "cancel_job":
        return _ok({"ok": jobs.cancel(arguments["job_id"])})

    return _err("unknown_tool", name)


async def _maybe_markdown_inline_or_job(
    *,
    resolved: pdf_source.Resolved,
    pages: list[int] | None,
    password: str | None,
    kind: str,
) -> list[types.TextContent]:
    """Hybrid sync/async: small PDFs run inline; large ones queue a job.

    In stdio mode the job path still queues, then `wait_for_result`
    blocks until completion and returns the artifact inline — there's no
    HTTP server to download from.
    """
    info_dict = pdf_reader.info(resolved.path, password=password)
    if info_dict.get("is_encrypted") and not password:
        return _err("encrypted", "PDF is encrypted; pass `password`")
    page_count = int(info_dict.get("page_count") or 0)
    effective_pages = pages if pages else list(range(1, page_count + 1))
    if 0 < len(effective_pages) <= config.SYNC_PAGE_THRESHOLD:
        if kind == "read_markdown":
            return _ok(pdf_reader.read_markdown(resolved.path, pages=pages, password=password))
        return _ok(pdf_reader.read_chunks(resolved.path, pages=pages, password=password))

    if kind == "read_markdown":
        job_id, _ = jobs.start_read_markdown(resolved=resolved, pages=pages, password=password)
    else:
        job_id, _ = jobs.start_read_chunks(resolved=resolved, pages=pages, password=password)

    if jobs.transport_mode() == "stdio":
        snap = jobs.wait_for_result(job_id)
        if snap.get("error"):
            return _err(snap["error"], json.dumps(snap.get("snapshot", {})))
        if snap["state"] != "done":
            return _err("job_failed", snap.get("error") or snap["state"])
        job_dir = outputs.resolve_job_dir(job_id)
        if job_dir is None:
            return _err("artifact_missing", "job dir missing")
        if kind == "read_markdown":
            return _ok({"markdown": outputs.read_result_markdown(job_dir)})
        return _ok(json.loads(outputs.read_result_json(job_dir)))

    # HTTP mode: return job handle, client polls.
    snap = jobs.get_status(job_id)
    return _ok(snap or {"job_id": job_id, "state": "pending"})
