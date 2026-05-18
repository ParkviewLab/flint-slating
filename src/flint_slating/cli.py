"""Top-level CLI: stdio by default, `serve` for the HTTP daemon.

Examples:

    python -m flint_slating               # stdio MCP (for claude_desktop_config.json / mcp.json)
    python -m flint_slating serve         # Streamable-HTTP MCP daemon on PORT
    python -m flint_slating serve --host 127.0.0.1 --port 35833

The container image's CMD invokes `serve` because stdio doesn't make
sense across a container boundary.
"""

from __future__ import annotations

import argparse
import logging
import sys

from flint_slating import stdio_entry
from flint_slating.config import HOST, PORT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="flint-slating", description="PDF-reading MCP server.")
    subparsers = parser.add_subparsers(dest="mode")

    serve = subparsers.add_parser("serve", help="Run the Streamable-HTTP daemon.")
    serve.add_argument("--host", default=HOST)
    serve.add_argument("--port", default=PORT, type=int)

    args = parser.parse_args(argv)

    if args.mode == "serve":
        _run_http(host=args.host, port=args.port)
        return

    # Default: stdio MCP.
    stdio_entry.main()


def _run_http(*, host: str, port: int) -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    uvicorn.run("flint_slating.app:app", host=host, port=port)
