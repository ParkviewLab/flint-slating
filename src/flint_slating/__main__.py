# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Entrypoint: `python -m flint_slating` -> uvicorn (default) or stdio.

Mirrors deco-assaying's CLI shape:

    flint-slating                      # HTTP (Streamable-HTTP MCP on PORT)
    flint-slating --transport http     # same
    flint-slating --transport stdio    # stdio MCP (for mcp.json integrations)
"""

from __future__ import annotations

import argparse
import logging

import anyio
import uvicorn

from flint_slating import jobs, pdf_reader
from flint_slating.config import HOST, PORT


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="flint-slating", description="PDF-reading MCP server.")
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default="http",
        help="MCP transport to use (default: http)",
    )
    return parser.parse_args()


async def _run_stdio() -> None:
    from mcp.server.stdio import stdio_server

    from flint_slating.mcp_server import mcp

    jobs.set_transport_mode("stdio")
    try:
        pdf_reader.warm_docling()
    except Exception as e:
        logging.getLogger(__name__).warning("docling warmup failed: %s", e)

    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options(),
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    if args.transport == "stdio":
        anyio.run(_run_stdio)
    else:
        uvicorn.run("flint_slating.app:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
