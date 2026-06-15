# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""HTTP routes for the Streamable-HTTP transport.

Adds `/health`, `/admin/version`, and `/outputs/{job_id}/*` alongside
the `/sse` MCP endpoint (mounted in `app.py`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import BaseModel

from flint_slating import config, jobs, outputs, pdf_reader
from flint_slating.mcp_server import mcp


def _safe_pkg_version(name: str) -> str:
    try:
        return _pkg_version(name)
    except PackageNotFoundError:
        return "unknown"


log = logging.getLogger(__name__)
_started_at = time.time()

router = APIRouter()
session_manager = StreamableHTTPSessionManager(app=mcp, stateless=True)


class MCPASGIApp:
    """Raw ASGI3 callable so Starlette doesn't wrap SSE in request_response."""

    async def __call__(self, scope, receive, send) -> None:
        await session_manager.handle_request(scope, receive, send)


mcp_asgi = MCPASGIApp()


# ---------------------------------------------------------------------------
# /health


class Health(BaseModel):
    ok: bool
    version: str
    uptime_seconds: float


@router.get("/health", response_model=Health, tags=["health"])
async def health() -> Health:
    return Health(ok=True, version=config.VERSION, uptime_seconds=time.time() - _started_at)


# ---------------------------------------------------------------------------
# /admin/version


class AdminVersion(BaseModel):
    version: str
    mcp_protocol_version: str
    docling_version: str
    pypdf_version: str
    docling_artifacts_path: str
    docling_model_loaded: bool


@router.get("/admin/version", response_model=AdminVersion, tags=["admin"])
async def admin_version() -> AdminVersion:
    # Reads pdf_reader's module-level converter without forcing init.
    converter_built = pdf_reader._docling_converter is not None
    return AdminVersion(
        version=config.VERSION,
        mcp_protocol_version=_safe_pkg_version("mcp"),
        docling_version=_safe_pkg_version("docling"),
        pypdf_version=_safe_pkg_version("pypdf"),
        docling_artifacts_path=str(config.DOCLING_ARTIFACTS_PATH),
        docling_model_loaded=converter_built,
    )


# ---------------------------------------------------------------------------
# /admin/jobs


@router.get("/admin/jobs", tags=["admin"])
async def admin_jobs(limit: int = 100, status: str | None = None) -> list[dict]:
    return jobs.list_jobs(limit=limit, status=status)


# ---------------------------------------------------------------------------
# /outputs/{job_id}/*


def _job_dir_or_404(job_id: str):
    job_dir = outputs.resolve_job_dir(job_id)
    if job_dir is None:
        raise HTTPException(status_code=404, detail="unknown_job_id")
    return job_dir


@router.get("/outputs/{job_id}/result.md", tags=["outputs"])
async def outputs_result_md(job_id: str) -> FileResponse:
    job_dir = _job_dir_or_404(job_id)
    target = job_dir / "result.md"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="result.md not present")
    return FileResponse(target, media_type="text/markdown")


@router.get("/outputs/{job_id}/result.json", tags=["outputs"])
async def outputs_result_json(job_id: str) -> FileResponse:
    job_dir = _job_dir_or_404(job_id)
    target = job_dir / "result.json"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="result.json not present")
    return FileResponse(target, media_type="application/json")


@router.get("/outputs/{job_id}/log.jsonl", tags=["outputs"])
async def outputs_log(job_id: str) -> FileResponse:
    job_dir = _job_dir_or_404(job_id)
    target = job_dir / "log.jsonl"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="log.jsonl not present")
    return FileResponse(target, media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Lifespan


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    uvlog = logging.getLogger("uvicorn.error")
    jobs.set_transport_mode("http")
    # Warm Docling off the request path. Don't fail startup if the model
    # is unavailable — first user call will surface a clean error.
    try:
        pdf_reader.warm_docling()
    except Exception as e:
        uvlog.warning("docling warmup failed: %s", e)
    async with session_manager.run():
        sweeper = asyncio.create_task(_sweeper_loop(), name="retention-sweeper")
        uvlog.info("flint-slating v%s ready (HTTP transport)", config.VERSION)
        try:
            yield
        finally:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper


async def _sweeper_loop() -> None:
    """Hourly retention sweep over OUTPUT_ROOT. Quiet on success."""
    if config.OUTPUT_EXPIRY_DAYS <= 0:
        return
    while True:
        try:
            removed = outputs.sweep_expired()
            if removed:
                log.info("retention sweeper removed %d expired job dirs", removed)
        except Exception as e:
            log.warning("retention sweep failed: %s", e)
        await asyncio.sleep(3600)
