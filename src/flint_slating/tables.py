# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Per-page table extraction via pdfplumber → Markdown.

pdfplumber is MIT-licensed and built on pdfminer.six (also MIT). It's
much faster than Docling for table-only queries on small page ranges,
which is the typical case ("give me the table on page 4").
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pdfplumber

log = logging.getLogger(__name__)


def find_tables(
    path: Path,
    *,
    pages: list[int] | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Extract tables across the given pages.

    Returns `{tables: [{page, index, markdown, n_rows, n_cols}], page_count: int}`.
    """
    out: list[dict[str, Any]] = []
    open_kwargs: dict[str, Any] = {}
    if password:
        open_kwargs["password"] = password
    with pdfplumber.open(str(path), **open_kwargs) as pdf:
        total = len(pdf.pages)
        selected = _normalize_pages(pages, total)
        for pno in selected:
            page = pdf.pages[pno]
            try:
                page_tables = page.extract_tables() or []
            except Exception as e:
                log.debug("pdfplumber table extract failed on page %d: %s", pno + 1, e)
                continue
            for idx, table in enumerate(page_tables):
                out.append(
                    {
                        "page": pno + 1,
                        "index": idx,
                        "markdown": _table_to_markdown(table),
                        "n_rows": len(table),
                        "n_cols": max((len(r) for r in table), default=0),
                    }
                )
        return {"tables": out, "page_count": total}


def _normalize_pages(pages: list[int] | None, total: int) -> list[int]:
    if not pages:
        return list(range(total))
    out: list[int] = []
    seen: set[int] = set()
    for p in pages:
        idx = int(p) - 1
        if 0 <= idx < total and idx not in seen:
            seen.add(idx)
            out.append(idx)
    return out


def _table_to_markdown(rows: list[list[Any]]) -> str:
    """Tiny Markdown table renderer. Empty rows / cells become blank."""
    if not rows:
        return ""
    norm: list[list[str]] = [[_clean_cell(c) for c in row] for row in rows]
    n_cols = max(len(r) for r in norm)
    for r in norm:
        if len(r) < n_cols:
            r.extend([""] * (n_cols - len(r)))
    header = norm[0]
    sep = ["---"] * n_cols
    body = norm[1:] if len(norm) > 1 else []
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _clean_cell(c: Any) -> str:
    if c is None:
        return ""
    s = str(c).replace("\n", " ").replace("|", "\\|").strip()
    return s
