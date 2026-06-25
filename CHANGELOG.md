<!--
SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>

SPDX-License-Identifier: MIT OR Apache-2.0
-->

# Changelog

All notable changes to this project are recorded here. Each release entry
has two parts:

- **Highlights** — a 2-3 sentence "what's new" paragraph generated at
  release time by an Anthropic-API call (see
  `scripts/generate_changelog.py`).
- **Categorized changes** — a list of merged commits since the previous
  tag, grouped by [Conventional Commit](https://www.conventionalcommits.org/)
  prefix, produced by [git-cliff](https://git-cliff.org/) using
  `cliff.toml`.

The release workflow on every tag push regenerates both, commits the new
section here, and uses the same content as the GitHub Release body.

<!--
  Keep-a-Changelog ordering: [Unreleased] at the top, then newest
  released version, then older versions. generate_changelog.py inserts
  new "## [vX.Y.Z] - YYYY-MM-DD" sections directly below [Unreleased].
  Don't remove the marker.
-->

## [Unreleased]

## [v0.1.6] - 2026-06-24

### Highlights

This is a maintenance release that bumps lagging GitHub Actions pins to their Node 24 floors, with no user-facing behavior changes.

### Docs

- V0.1.5 [skip ci] (e37d96f)

## [v0.1.5] - 2026-06-14

### Highlights

This release is housekeeping: the project is relicensed from MIT-only to the Rust-convention `MIT OR Apache-2.0` dual license, with per-file SPDX headers, REUSE compliance, and updated packaging metadata. CI also gains automated CHANGELOG and GitHub Release generation on tag push, with the existing v0.1.0–v0.1.4 entries backfilled. No runtime behavior changes.

## [v0.1.4] - 2026-05-18

### Highlights

Torch and torchvision are now pinned to PyTorch's CPU-only wheel index, removing all NVIDIA CUDA libraries from the distribution and shrinking the container image by roughly 3–4 GB; on Linux and Windows, Docling layout-model inference now runs on CPU rather than CUDA, while Apple Silicon continues to use MPS. A new THIRD_PARTY_LICENSES.md documents every runtime dependency grouped by license family.

## [v0.1.2] - 2026-05-18

### Highlights

This is a maintenance release that bumps CI action pins to the Node 24 line ahead of GitHub's June 2026 deprecation of Node 20 actions, with no user-facing changes to the MCP server itself.

## [v0.1.1] - 2026-05-18

### Highlights

The Docling model is no longer pre-fetched during the Docker image build, which was causing multi-arch release builds to stall under arm64 QEMU emulation. The model is now downloaded on first use, with daemon warmup occurring at process startup rather than on the request path; operators wanting a hot start can mount a pre-populated /opt/docling-models volume.

## [v0.1.0] - 2026-05-18

### Highlights

Initial release of an MCP server that exposes PDFs to LLM agents as Markdown, metadata, outline, images, and tables, built on a permissive PDF stack (Docling, pypdf, pdfplumber) with copyleft dependencies blocked in CI. A single entry point serves both transports via `--transport {http,stdio}`, defaulting to Streamable-HTTP, with stdio available for `mcp.json` integrations. Conversion is hybrid: small PDFs run inline while larger ones queue a background job, with results delivered inline under stdio.

