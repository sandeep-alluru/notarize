"""SILENT-SUCCESS - exit 0 / success claim with degraded or failed steps.

Farm: assemble exits 0 degraded (Foundry-class).
Public: DiagChain / MAFIA - audit trails must not rubber-stamp bad runs.
"""

from __future__ import annotations

import pytest

from notarize.closed_loop import (
    ClosedLoopError,
    assert_no_silent_success,
    degraded_step_indices,
    failed_step_indices,
    gate_claimed_success,
    gate_trace,
    step_is_degraded,
    step_is_failed,
)
from notarize.trace import AgentTrace, TraceStep


def _trace(results: list[str], *, trace_id: str = "ss-001") -> AgentTrace:
    steps = [TraceStep(i, f"tool_call:step{i}", f"obs{i}", r) for i, r in enumerate(results)]
    return AgentTrace(trace_id, "agent", "assemble episode", steps, created_at=1000.0)


def test_failed_step_detected() -> None:
    t = _trace(["success", "error", "success"])
    assert failed_step_indices(t) == [1]
    assert step_is_failed(t.steps[1]) is True
    assert step_is_failed(t.steps[0]) is False


def test_degraded_step_detected() -> None:
    t = _trace(["success", "degraded", "success"])
    assert degraded_step_indices(t) == [1]
    assert step_is_degraded(t.steps[1]) is True


def test_degraded_in_observation_text() -> None:
    steps = [
        TraceStep(0, "assemble", "partially complete, missing artifacts", "success"),
    ]
    t = AgentTrace("ss-obs", "agent", "assemble", steps, created_at=1.0)
    assert degraded_step_indices(t) == [0]


def test_gate_trace_refuses_failed_steps_despite_valid_chain() -> None:
    """Hash chain OK but step failed → not PASS (SILENT-SUCCESS)."""
    t = _trace(["success", "failed", "success"])
    out = gate_trace(t)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1
    assert out.silent_success is True
    assert out.failed_step_indices == (1,)
    assert "SILENT-SUCCESS" in out.reason


def test_gate_trace_refuses_degraded() -> None:
    t = _trace(["success", "partial", "success"])
    out = gate_trace(t)
    assert out.ok is False
    assert out.silent_success is True
    assert out.degraded_step_indices == (1,)


def test_gate_trace_can_opt_out_of_degraded_refuse() -> None:
    t = _trace(["success", "degraded", "success"])
    out = gate_trace(t, refuse_degraded=False, refuse_failed_steps=False)
    assert out.ok is True
    assert out.verdict == "PASS"


def test_clean_trace_still_passes() -> None:
    t = _trace(["success", "success", "success"])
    out = gate_trace(t)
    assert out.ok is True
    assert out.silent_success is False
    assert out.failed_step_indices == ()
    assert out.degraded_step_indices == ()


def test_claimed_success_exit_0_with_degraded_fails() -> None:
    """Assemble exits 0 degraded - the load-bearing SILENT-SUCCESS fixture."""
    t = _trace(["success", "degraded", "success"], trace_id="assemble-degraded")
    out = gate_claimed_success(claimed_ok=True, claimed_exit_code=0, trace=t)
    assert out.ok is False
    assert out.exit_code == 1
    assert out.silent_success is True
    assert "claimed success" in out.reason.lower() or "SILENT-SUCCESS" in out.reason


def test_claimed_success_with_error_step_fails() -> None:
    t = _trace(["success", "error", "success"])
    out = gate_claimed_success(True, 0, t)
    assert out.ok is False
    assert out.silent_success is True
    assert 1 in out.failed_step_indices


def test_claimed_success_clean_passes() -> None:
    t = _trace(["success", "success"])
    out = gate_claimed_success(True, 0, t)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.silent_success is False


def test_claimed_failure_with_failed_steps_is_aligned() -> None:
    t = _trace(["success", "error"])
    out = gate_claimed_success(False, 1, t)
    assert out.ok is False
    assert out.silent_success is False
    assert out.exit_code == 1


def test_assert_no_silent_success_raises() -> None:
    t = _trace(["degraded"])
    with pytest.raises(ClosedLoopError, match=r"SILENT-SUCCESS|FAIL"):
        assert_no_silent_success(True, 0, t)


def test_assert_no_silent_success_returns_on_clean() -> None:
    t = _trace(["success"])
    out = assert_no_silent_success(True, 0, t)
    assert out.ok is True


def test_to_dict_includes_silent_success_fields() -> None:
    t = _trace(["error"])
    payload = gate_trace(t).to_dict()
    assert payload["silent_success"] is True
    assert payload["failed_step_indices"] == [0]
    assert payload["ok"] is False
