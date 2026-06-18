"""Tests for notarize FastAPI REST endpoints."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from notarize.api import app
from notarize.trace import AgentTrace, TraceStep

client = TestClient(app)


def _valid_trace_dict(trace_id: str = "api-trace") -> dict:
    steps = [
        TraceStep(0, "tool_call:search", "found results", "success"),
        TraceStep(1, "tool_call:write", "wrote output", "success"),
    ]
    trace = AgentTrace(trace_id, "api-agent", "test task", steps, created_at=0.0)
    return trace.to_dict()


def _pii_trace_dict() -> dict:
    steps = [TraceStep(0, "Contact user@secret.com", "sent to 10.0.0.1", "success")]
    trace = AgentTrace("pii-trace", "agent", "test", steps, created_at=0.0)
    return trace.to_dict()


# ── /health ───────────────────────────────────────────────────────────────────


def test_health_returns_ok() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def test_app_title() -> None:
    assert app.title == "notarize API"


# ── /verify ───────────────────────────────────────────────────────────────────


def test_verify_valid_trace(tmp_path) -> None:
    r = client.post(
        "/verify",
        json={"trace": _valid_trace_dict(), "db": str(tmp_path / "traces.db")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] == "verified"
    assert "checks_passed" in data


def test_verify_returns_trace_id(tmp_path) -> None:
    r = client.post(
        "/verify",
        json={"trace": _valid_trace_dict("my-trace"), "db": str(tmp_path / "traces.db")},
    )
    assert r.status_code == 200
    assert r.json()["trace_id"] == "my-trace"


def test_verify_invalid_trace_dict(tmp_path) -> None:
    r = client.post(
        "/verify",
        json={"trace": {"bad": "data"}, "db": str(tmp_path / "traces.db")},
    )
    assert r.status_code == 422


def test_verify_empty_steps_trace(tmp_path) -> None:
    trace = AgentTrace("empty-t", "agent", "task", [], created_at=0.0)
    r = client.post(
        "/verify",
        json={"trace": trace.to_dict(), "db": str(tmp_path / "traces.db")},
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "verified"


# ── /scrub ────────────────────────────────────────────────────────────────────


def test_scrub_valid_trace() -> None:
    r = client.post("/scrub", json={"trace": _pii_trace_dict()})
    assert r.status_code == 200
    data = r.json()
    assert "scrubbed_trace" in data
    assert "replacements_count" in data
    assert "patterns_matched" in data


def test_scrub_removes_email() -> None:
    r = client.post("/scrub", json={"trace": _pii_trace_dict()})
    assert r.status_code == 200
    data = r.json()
    assert "user@secret.com" not in json.dumps(data["scrubbed_trace"]["steps"])


def test_scrub_returns_original_trace_id() -> None:
    r = client.post("/scrub", json={"trace": _pii_trace_dict()})
    assert r.status_code == 200
    assert r.json()["original_trace_id"] == "pii-trace"


def test_scrub_invalid_trace() -> None:
    r = client.post("/scrub", json={"trace": {"bad": "data"}})
    assert r.status_code == 422


# ── /traces ───────────────────────────────────────────────────────────────────


def test_list_traces_empty(tmp_path) -> None:
    r = client.get("/traces", params={"db": str(tmp_path / "t.db")})
    assert r.status_code == 200
    assert r.json()["traces"] == []


def test_list_traces_after_verify(tmp_path) -> None:
    db = str(tmp_path / "traces.db")
    client.post("/verify", json={"trace": _valid_trace_dict("lt-1"), "db": db})
    r = client.get("/traces", params={"db": db})
    assert r.status_code == 200
    assert len(r.json()["traces"]) == 1


# ── /trace/{trace_id} ─────────────────────────────────────────────────────────


def test_get_trace_after_verify(tmp_path) -> None:
    db = str(tmp_path / "traces.db")
    client.post("/verify", json={"trace": _valid_trace_dict("gt-1"), "db": db})
    r = client.get("/trace/gt-1", params={"db": db})
    assert r.status_code == 200
    assert r.json()["trace_id"] == "gt-1"


def test_get_trace_not_found(tmp_path) -> None:
    r = client.get("/trace/nonexistent", params={"db": str(tmp_path / "t.db")})
    assert r.status_code == 404
