"""FastAPI app construction for the HTTP transport.

Logging is configured by the entry point; importing this module does not
touch the root logger.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.routing import Route

from flint_slating.config import VERSION
from flint_slating.routes import lifespan, mcp_asgi, router

app = FastAPI(
    title="flint-slating",
    version=VERSION,
    description=(
        "PDF-reading MCP server. The /sse endpoint exposes the MCP "
        "Streamable-HTTP transport; /outputs/{job_id}/* serves finished "
        "job artifacts."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=256)
# Streamable HTTP MCP transport at /sse, mounted as raw ASGI3 so
# Starlette doesn't wrap SSE in request_response (which would break
# streaming).
app.router.routes.append(Route("/sse", endpoint=mcp_asgi, methods=["GET", "POST", "DELETE"]))
app.include_router(router)
