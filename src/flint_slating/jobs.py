# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Background jobs for big PDF conversions.

A job runs the full Docling pipeline on a single PDF and writes the
result to `OUTPUT_ROOT/{job_id}/`. The hybrid sync/async split lives in
`tools.py` — small PDFs are converted inline; large ones (`page_count >
SYNC_PAGE_THRESHOLD`) call `start_read_markdown` or `start_read_chunks`
and get a `job_id` back immediately.

Workers run on a single background thread per job, daemon-flagged so the
process can exit cleanly. There's no process pool here — Docling already
holds a per-process layout model, and parallel runs would step on its
cache.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal

from flint_slating import config, outputs, pdf_reader, pdf_source

log = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()

JobKind = Literal["read_markdown", "read_chunks"]
_TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})

# Whether jobs should emit HTTP-style result URLs (set by the entry
# point). Stdio mode flips this off — there's no HTTP server backing
# `/outputs/{id}/...`.
_mode: Literal["stdio", "http"] = "http"


def set_transport_mode(mode: Literal["stdio", "http"]) -> None:
    global _mode
    _mode = mode


def transport_mode() -> Literal["stdio", "http"]:
    return _mode


# ---------------------------------------------------------------------------
# Public entry points (called from tools.py)


def start_read_markdown(
    *,
    resolved: pdf_source.Resolved,
    pages: list[int] | None,
    password: str | None,
) -> tuple[str, Path]:
    return _start_job(
        kind="read_markdown",
        resolved=resolved,
        pages=pages,
        password=password,
    )


def start_read_chunks(
    *,
    resolved: pdf_source.Resolved,
    pages: list[int] | None,
    password: str | None,
) -> tuple[str, Path]:
    return _start_job(
        kind="read_chunks",
        resolved=resolved,
        pages=pages,
        password=password,
    )


def get_status(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return _public_view(job)


def cancel(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return False
        if job["status"] in _TERMINAL_STATES:
            return True
        job["_cancel"] = True
        return True


def is_active(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        return bool(job and job["status"] not in _TERMINAL_STATES)


def drop(job_id: str) -> bool:
    with _lock:
        if job_id in _jobs:
            del _jobs[job_id]
            return True
        return False


def list_jobs(*, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(limit, max(1, config.JOB_HISTORY_MAX)))
    with _lock:
        snapshots = [_public_view(j) for j in reversed(list(_jobs.values()))]
    if status:
        snapshots = [s for s in snapshots if s["state"] == status]
    return snapshots[:limit]


def wait_for_result(job_id: str, timeout_seconds: float = 1800.0) -> dict[str, Any]:
    """Block until `job_id` reaches a terminal state. Used by the stdio
    transport to keep the request inline (no separate `get_job_*` calls)."""
    deadline = time.time() + timeout_seconds
    while True:
        snap = get_status(job_id)
        if snap is None:
            return {"error": "unknown_job_id"}
        if snap["state"] in _TERMINAL_STATES:
            return snap
        if time.time() > deadline:
            return {"error": "timeout", "snapshot": snap}
        time.sleep(0.25)


# ---------------------------------------------------------------------------
# Internals


def _start_job(
    *,
    kind: JobKind,
    resolved: pdf_source.Resolved,
    pages: list[int] | None,
    password: str | None,
) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex[:16]
    job_dir = outputs.prepare_job_dir(job_id)
    now = time.time()
    job: dict[str, Any] = {
        "job_id": job_id,
        "kind": kind,
        "source_path": str(resolved.path),
        "sha256": resolved.sha256,
        "size": resolved.size,
        "pages": pages or [],
        "password": password,  # not serialized to disk; only kept in-memory
        "job_dir": str(job_dir),
        "status": "pending",
        "started_at": now,
        "finished_at": None,
        "error": None,
        "_cancel": False,
    }
    with _lock:
        _jobs[job_id] = job
        _evict_if_full(now_inserting_id=job_id)

    threading.Thread(target=_run, args=(job_id,), name=f"pdf-job-{job_id}", daemon=True).start()
    return job_id, job_dir


def _evict_if_full(*, now_inserting_id: str) -> None:
    cap = max(1, config.JOB_HISTORY_MAX)
    while len(_jobs) > cap:
        for jid, job in _jobs.items():
            if jid != now_inserting_id and job["status"] in _TERMINAL_STATES:
                del _jobs[jid]
                break
        else:
            return


def _set_status(job_id: str, status: str, *, error: str | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job["status"] = status
        if status in _TERMINAL_STATES:
            job["finished_at"] = time.time()
        if error is not None:
            job["error"] = error


def _run(job_id: str) -> None:
    with _lock:
        job = _jobs[job_id]
        kind: JobKind = job["kind"]
        path = Path(job["source_path"])
        pages = job["pages"] or None
        password = job["password"]
        job_dir = Path(job["job_dir"])

    log_path = job_dir / "log.jsonl"
    _emit(log_path, {"event": "started", "kind": kind})
    _set_status(job_id, "running")
    try:
        if kind == "read_markdown":
            result = pdf_reader.read_markdown(path, pages=pages, password=password)
            outputs.write_result_markdown(job_dir, result["markdown"])
            outputs.write_result_json(job_dir, json.dumps({"page_count": result["page_count"]}))
        elif kind == "read_chunks":
            result = pdf_reader.read_chunks(path, pages=pages, password=password)
            outputs.write_result_json(job_dir, json.dumps(result))
        else:
            raise ValueError(f"unknown job kind: {kind}")
        _emit(log_path, {"event": "done"})
        _set_status(job_id, "done")
    except pdf_reader.EncryptedPdfError as e:
        _emit(log_path, {"event": "failed", "error": str(e)})
        _set_status(job_id, "failed", error=f"encrypted: {e}")
    except Exception as e:
        log.exception("job %s failed", job_id)
        _emit(log_path, {"event": "failed", "error": str(e)})
        _set_status(
            job_id,
            "failed",
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        )


def _public_view(job: dict[str, Any]) -> dict[str, Any]:
    job_id = job["job_id"]
    state = job["status"]
    output_url: str | None = None
    if state == "done" and _mode == "http":
        suffix = "result.md" if job["kind"] == "read_markdown" else "result.json"
        output_url = f"{config.PUBLIC_BASE_URL}/outputs/{job_id}/{suffix}"
    return {
        "job_id": job_id,
        "kind": job["kind"],
        "state": state,
        "output_url": output_url,
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "error": job["error"],
    }


def _emit(log_path: Path, event: dict[str, Any]) -> None:
    line = {"ts": time.time(), **event}
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass
