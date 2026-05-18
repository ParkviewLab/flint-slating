"""HTTP-mode routes: /health, /admin/version, /outputs/* 404 behavior."""

from __future__ import annotations


def test_health(mcp_client):
    r = mcp_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "version" in body


def test_admin_version(mcp_client):
    r = mcp_client.get("/admin/version")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert "docling_version" in body
    assert "pypdf_version" in body


def test_outputs_404_for_unknown_job(mcp_client):
    r = mcp_client.get("/outputs/does-not-exist/result.md")
    assert r.status_code == 404


def test_admin_jobs_empty_list(mcp_client):
    r = mcp_client.get("/admin/jobs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
