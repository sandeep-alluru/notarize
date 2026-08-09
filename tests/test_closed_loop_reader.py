"""Closed-loop reader - empty/tampered traces must fail loudly (L1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from notarize.closed_loop import (
    ClosedLoopError,
    GateOutcome,
    assert_trace_verified,
    gate_trace,
)
from notarize.trace import AgentTrace, TraceStep


def _valid_trace(trace_id: str = "trace-cl-001") -> AgentTrace:
    steps = [
        TraceStep(0, "tool_call:search", "found results", "success"),
        TraceStep(1, "tool_call:read", "read content", "success"),
        TraceStep(2, "tool_call:write", "wrote output", "success"),
    ]
    return AgentTrace(trace_id, "test-agent", "do stuff", steps, created_at=1000.0)


def test_empty_trace_fails_loud() -> None:
    empty = AgentTrace("empty", "agent", "task", [], created_at=0.0)
    out = gate_trace(empty)
    assert isinstance(out, GateOutcome)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.verification is None
    assert "empty" in out.reason.lower()


def test_valid_trace_passes() -> None:
    out = gate_trace(_valid_trace())
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0
    assert out.verification is not None
    assert out.verification.verdict == "verified"
    payload = out.to_dict()
    assert payload["ok"] is True
    assert payload["verification"]["verdict"] == "verified"


def test_tampered_chain_fails() -> None:
    t = _valid_trace()
    t.steps[1].parent_id = "tampered_value"
    out = gate_trace(t)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.verification is not None
    assert "hash_chain_integrity" in out.verification.checks_failed


def test_missing_file_fails_loud(tmp_path: Path) -> None:
    out = gate_trace(tmp_path / "missing.json")
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "not found" in out.reason.lower()


def test_assert_trace_verified_raises_on_empty() -> None:
    with pytest.raises(ClosedLoopError, match="FAIL_LOUD"):
        assert_trace_verified(AgentTrace("e", "a", "t", [], created_at=0.0))


def test_assert_trace_verified_returns_on_valid() -> None:
    out = assert_trace_verified(_valid_trace())
    assert out.ok is True
