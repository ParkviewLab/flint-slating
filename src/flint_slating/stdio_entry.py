"""stdio MCP transport entry.

Spawned via `python -m flint_slating` (no args) — see `cli.py`. The
process reads MCP frames from stdin, writes them to stdout. Logging is
forced to stderr to keep stdout reserved for MCP.

The Docling layout model is warmed at startup so the first user-facing
call doesn't pay the model-download cost.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from flint_slating import jobs, pdf_reader
from flint_slating.mcp_server import mcp


async def _run() -> None:
    jobs.set_transport_mode("stdio")
    try:
        pdf_reader.warm_docling()
    except Exception as e:  # never fatal — first tool call will surface a clean error
        logging.getLogger(__name__).warning("docling warmup failed: %s", e)

    async with stdio_server() as (read, write):
        await mcp.run(
            read,
            write,
            InitializationOptions(
                server_name=mcp.name,
                server_version=getattr(mcp, "version", "0.0.0"),
                capabilities=mcp.get_capabilities(notification_options=None, experimental_capabilities={}),
            ),
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(_run())
