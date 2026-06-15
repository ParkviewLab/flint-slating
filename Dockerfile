# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# CA certs for httpx URL downloads. No system PDF tools needed — the
# whole PDF stack is pure-Python wheels (docling, pypdf, pdfplumber,
# pypdfium2). git is dev-time only.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Resolve deps first so they cache across source changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# README.md is part of the package metadata (pyproject.toml -> readme).
COPY README.md ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# Docling lays its layout model down on first user-facing call. We do
# NOT pre-fetch it at build time — that step executes Python code under
# arm64 QEMU emulation when buildx is producing the multi-arch image,
# which dominated wall-clock (~9 min and counting on v0.1.0). The first
# request after container start pays the download cost instead.
# DOCLING_ARTIFACTS_PATH points the cache at a stable location so an
# operator can pre-populate it via volume mount if they want a hot start.
ENV PYTHONUNBUFFERED=1 \
    DOCLING_ARTIFACTS_PATH=/opt/docling-models \
    OUTPUT_ROOT=/data/output \
    CACHE_ROOT=/data/cache \
    PORT=35833 \
    HOST=0.0.0.0

EXPOSE 35833
VOLUME ["/data"]

# Container always runs the HTTP transport — stdio across a container
# boundary doesn't make sense. HTTP is the default; --transport http is
# explicit so anyone reading the Dockerfile knows what mode it runs in.
CMD ["uv", "run", "python", "-m", "flint_slating", "--transport", "http"]
