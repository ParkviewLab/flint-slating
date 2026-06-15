# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Per-job output directory layout + path-safe artifact reads.

Each job gets `config.OUTPUT_ROOT/{job_id}/` with:
    result.md      — full Markdown (when produced)
    result.json    — chunked / structured output (when produced)
    log.jsonl      — append-only event log
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, TypedDict

from flint_slating import config


class OutputError(Exception):
    """Raised when a /outputs/... request can't be served safely."""


class ArtifactMissing(OutputError):
    """A specific artifact (e.g. result.md) hasn't been written yet."""


class JobDirRow(TypedDict):
    job_id: str
    size: int
    mtime: float


def prepare_job_dir(job_id: str) -> Path:
    """Allocate `OUTPUT_ROOT/{job_id}/` for a fresh job."""
    root = config.OUTPUT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    job_dir = (root / job_id).resolve(strict=False)
    if not _is_under(job_dir, root.resolve()):
        raise OutputError(f"refusing to create job dir outside OUTPUT_ROOT: {job_id!r}")
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def resolve_job_dir(job_id: str) -> Path | None:
    """Find a job's output dir on disk under `config.OUTPUT_ROOT`."""
    root = config.OUTPUT_ROOT.resolve()
    candidate = (config.OUTPUT_ROOT / job_id).resolve(strict=False)
    if candidate.is_dir() and _is_under(candidate, root):
        return candidate
    return None


def safe_subpath(job_dir: Path, rel: str) -> Path:
    """Resolve `rel` under `job_dir` and reject anything that escapes."""
    cleaned = rel.lstrip("/").lstrip("\\")
    if not cleaned:
        return job_dir
    target = (job_dir / cleaned).resolve(strict=False)
    if not _is_under(target, job_dir.resolve()):
        raise OutputError(f"path escapes job dir: {rel!r}")
    return target


def read_result_markdown(job_dir: Path) -> str:
    target = job_dir / "result.md"
    if not target.is_file():
        raise ArtifactMissing("result.md not present")
    return target.read_text(encoding="utf-8")


def read_result_json(job_dir: Path) -> str:
    target = job_dir / "result.json"
    if not target.is_file():
        raise ArtifactMissing("result.json not present")
    return target.read_text(encoding="utf-8")


def write_result_markdown(job_dir: Path, markdown: str) -> Path:
    target = job_dir / "result.md"
    target.write_text(markdown, encoding="utf-8")
    return target


def write_result_json(job_dir: Path, payload: str) -> Path:
    target = job_dir / "result.json"
    target.write_text(payload, encoding="utf-8")
    return target


def list_outputs_root() -> list[JobDirRow]:
    root = config.OUTPUT_ROOT
    if not root.is_dir():
        return []
    rows: list[JobDirRow] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        size = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
        rows.append(JobDirRow(job_id=child.name, size=size, mtime=child.stat().st_mtime))
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows


def remove_job_dir(job_dir: Path) -> None:
    shutil.rmtree(job_dir, ignore_errors=False)


def sweep_expired(now: float | None = None) -> int:
    """Remove job dirs older than `OUTPUT_EXPIRY_DAYS`. Returns count removed."""
    if config.OUTPUT_EXPIRY_DAYS <= 0:
        return 0
    now = now if now is not None else time.time()
    cutoff = now - (config.OUTPUT_EXPIRY_DAYS * 86400)
    removed = 0
    if not config.OUTPUT_ROOT.is_dir():
        return 0
    for child in config.OUTPUT_ROOT.iterdir():
        if not child.is_dir():
            continue
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _ensure_dict(_o: Any) -> dict[str, Any]:
    """Stub for future schema validation hook."""
    return _o
