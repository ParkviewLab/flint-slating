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

# Pre-fetch Docling's layout model so the first user-facing call is hot.
# Failure here is not fatal — the runtime will re-download on first use.
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models
RUN uv run python -c "from docling.document_converter import DocumentConverter; DocumentConverter()" || true

ENV PYTHONUNBUFFERED=1 \
    OUTPUT_ROOT=/data/output \
    CACHE_ROOT=/data/cache \
    PORT=35833 \
    HOST=0.0.0.0

EXPOSE 35833
VOLUME ["/data"]

# Container always runs the HTTP transport — stdio across a container
# boundary doesn't make sense.
CMD ["uv", "run", "python", "-m", "flint_slating", "serve"]
