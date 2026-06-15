# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Transport-agnostic MCP `Server` instance.

Both the stdio entry (`stdio_entry.py`) and the HTTP routes (`routes.py`)
import the `mcp` object from here. Tool registration happens at import
time so either transport sees the same tool catalog.
"""

from __future__ import annotations

from mcp import types
from mcp.server import Server

from flint_slating import tools
from flint_slating.config import VERSION

mcp: Server = Server("flint-slating", version=VERSION)


@mcp.list_tools()
async def _list_tools() -> list[types.Tool]:
    return tools.TOOLS


@mcp.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    return await tools.dispatch(name, arguments)
