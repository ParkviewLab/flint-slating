<!--
SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>

SPDX-License-Identifier: MIT OR Apache-2.0
-->

# flint-slating

MCP server that reads PDFs and exposes them to LLM consumers as
structured Markdown, plus the usual ancillaries: metadata, outline,
images, tables.

Designed to pair with a separate "wiki" MCP server that handles the
*writing* side — an agent calls `flint-slating` to read PDFs and another
MCP to persist notes about them into a frontmattered-markdown knowledge
base.

## What it does

Built on a permissive-license PDF stack:

| Library | License | Role |
|---|---|---|
| [Docling](https://github.com/docling-project/docling) | MIT | PDF → Markdown with heading hierarchy, multi-column reading order, and Markdown tables |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3 | metadata, TOC, page count, encryption checks, image enumeration |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | MIT | per-page table extraction |

**There is no PyMuPDF, no MuPDF, no AGPL or GPL anywhere in the
dependency tree.** A CI license-check job rejects PRs that pull in
copyleft transitive deps.

## Transports

Two transports off the same MCP server, selected via `--transport`:

| Transport | Run via | Use case |
|---|---|---|
| **Streamable-HTTP** (default) | `uvx flint-slating` or `--transport http` | Long-lived local daemon, container, or shared service. |
| **stdio** | `uvx flint-slating --transport stdio` | The standard MCP integration shape — drop into `claude_desktop_config.json` or any `mcp.json`. |

## Run

### As an HTTP daemon (default)

```bash
uvx flint-slating                    # listens on PORT (default 35833)
curl http://127.0.0.1:35833/health
```

Or pin it:

```bash
uv tool install flint-slating
flint-slating
```

### As a stdio MCP server

```bash
uvx flint-slating --transport stdio
```

Wire into Claude Code's MCP config:

```json
{
  "mcpServers": {
    "flint-slating": {
      "command": "uvx",
      "args": ["flint-slating", "--transport", "stdio"]
    }
  }
}
```

### Docker

```bash
docker run --rm \
  -p 35833:35833 \
  -v $(pwd)/pdfs:/pdfs:ro \
  -v flint-slating-data:/data \
  ghcr.io/parkviewlab/flint-slating:latest
```

Or use [`docker-compose.yml`](docker-compose.yml) for a persistent stack.

## MCP tools

All PDF tools take a `source` argument with one of:

- `{"path": "/abs/path/to/file.pdf"}` — local file
- `{"url": "https://..."}` — streamed to a content-addressed cache
- `{"bytes_b64": "...", "filename": "x.pdf"}` — base64 upload (size-capped)

| Tool | What it does |
|---|---|
| `pdf_info` | `{page_count, metadata, is_encrypted, sha256}` |
| `pdf_toc` | flat outline `[{level, title, page}]` |
| `pdf_read_text` | plain text by page range (fast — pypdf, no ML) |
| `pdf_read_markdown` | high-quality Markdown via Docling (hybrid sync/async — see below) |
| `pdf_read_chunks` | per-page Markdown chunks with tables/images/toc_items (hybrid sync/async) |
| `pdf_list_images` | enumerate images: `[{page, index, name, width, height, ext}]` |
| `pdf_extract_image` | base64 bytes of one image |
| `pdf_find_tables` | per-page Markdown tables via pdfplumber |
| `get_job_status` | poll a background job |
| `get_job_result` | fetch a finished job's artifact |
| `cancel_job` | cancel a running job |

### Hybrid sync/async

`pdf_read_markdown` and `pdf_read_chunks` run inline when
`page_count <= SYNC_PAGE_THRESHOLD` (default 20). For larger PDFs they
queue a background job and return a `job_id` — poll `get_job_status`
until `state=="done"`, then call `get_job_result` (or, in HTTP mode,
fetch `output_url` directly).

**stdio mode** transparently waits for the job inline — there's no HTTP
server to download from, so the originating tool call blocks until the
result is ready and returns it directly.

## HTTP endpoints (HTTP mode only)

- `GET /health` — `{ok, version, uptime_seconds}`
- `GET /admin/version` — package and dependency versions, Docling model status
- `GET /admin/jobs` — recent job list
- `GET /outputs/{job_id}/result.md` — finished Markdown
- `GET /outputs/{job_id}/result.json` — finished chunked output
- `GET /outputs/{job_id}/log.jsonl` — append-only job log
- `POST /sse` — MCP Streamable-HTTP transport

## Configuration

| Env var | Default (daemon) | Default (container) | Purpose |
|---|---|---|---|
| `PORT` | `35833` | `35833` | HTTP bind port |
| `HOST` | `0.0.0.0` | `0.0.0.0` | HTTP bind address |
| `OUTPUT_ROOT` | `./output` | `/data/output` | Per-job output dirs |
| `CACHE_ROOT` | `./cache` | `/data/cache` | Materialized URL / base64 PDFs |
| `OUTPUT_EXPIRY_DAYS` | `7` | `7` | Sweep finished jobs older than N days |
| `MAX_INLINE_PDF_BYTES` | `25 MB` | `25 MB` | Cap on base64 upload size |
| `MAX_URL_PDF_BYTES` | `200 MB` | `200 MB` | Cap on URL download size |
| `SYNC_PAGE_THRESHOLD` | `20` | `20` | Inline-vs-job cutoff for Markdown conversion |
| `DOCLING_ARTIFACTS_PATH` | `~/.cache/docling` | `/opt/docling-models` | Docling layout-model cache |
| `ENABLE_OCR` | `false` | `false` | Enable Docling OCR (Tesseract required) |
| `PUBLIC_BASE_URL` | `http://localhost:35833` | `http://localhost:35833` | Used to build `output_url` |

## Resource notes

- Docling downloads a ~200–500 MB layout model on first use. The
  container image does **not** pre-fetch it (pre-fetching dominated
  multi-arch build time under QEMU); the daemon warms it on startup,
  and the first user-facing call pays the download. Operators can
  populate `DOCLING_ARTIFACTS_PATH` (default `/opt/docling-models` in
  the container) via volume mount for a hot start.
- pypdf, pdfplumber, and the URL / base64 paths are fast and have no ML
  overhead — use `pdf_info`, `pdf_toc`, `pdf_read_text`, and
  `pdf_find_tables` whenever Markdown isn't strictly needed.

## Releasing

Tag-driven CI publishes to both PyPI (`flint-slating`) and GHCR
(`ghcr.io/parkviewlab/flint-slating`):

```bash
# Bump version in pyproject.toml first, then:
git tag v0.1.0
git push origin v0.1.0
```

The release workflow refuses tags that don't match `pyproject.toml`'s
`version`, or that aren't on `origin/main`.

### Commit message convention

After the publish jobs, a **changelog** job generates the new `CHANGELOG.md` section — an LLM-written "Highlights" paragraph plus a [`git-cliff`](https://git-cliff.org/) categorized commit list — commits it back to `main`, and creates the GitHub Release with the same content as its body. Categorization uses [Conventional Commits](https://www.conventionalcommits.org/) prefixes (see [`cliff.toml`](cliff.toml)):

| Prefix | Section | Notes |
|---|---|---|
| `feat:` | Features | user-visible |
| `fix:` | Bug fixes | user-visible |
| `perf:` | Performance | user-visible |
| `refactor:` | Refactor | |
| `docs:` | Docs | |
| `test:` | Tests | |
| `chore:` / `ci:` / `build:` / `style:` | _(dropped)_ | not surfaced in CHANGELOG |

Squash-merge PRs use the PR title as the commit subject — so the **PR title** is what needs the prefix. Commits without a recognised prefix are silently dropped from the CHANGELOG (still in git history). The "Highlights" paragraph requires the `ANTHROPIC_API_KEY` org-level secret; if the LLM call fails, a placeholder lands and the release still ships.

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or
  <http://www.apache.org/licenses/LICENSE-2.0>), or
- MIT license ([LICENSE-MIT](LICENSE-MIT) or
  <http://opensource.org/licenses/MIT>)

at your option. In SPDX terms: `MIT OR Apache-2.0`.

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in this work by you shall be dual-licensed as above, without any
additional terms or conditions. See [LICENSING.md](LICENSING.md).

flint-slating only depends on permissive-licensed libraries; the CI
`license-check` job enforces this on every PR. torch and torchvision are pinned
to the [CPU-only PyTorch wheel index](https://download.pytorch.org/whl/cpu) so
the distribution does not bundle NVIDIA's proprietary CUDA libraries. Inference
runs on CPU on Linux/Windows and on MPS (Metal) on Apple Silicon. See
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for the per-dependency
license breakdown.

---
<sub>© 2026 Gary Frattarola · Licensed under [MIT](LICENSE-MIT) OR [Apache-2.0](LICENSE-APACHE) · part of [ParkviewLab](https://github.com/ParkviewLab)</sub>
