"""Tests for ConsistencyVerifier and VerificationResult from tracemarket.verifier."""

from __future__ import annotations

import pytest

from tracemarket.trace import AgentTrace, TraceStep
from tracemarket.verifier import ConsistencyVerifier, VerificationResult


@pytest.fixture
def verifier() -> ConsistencyVerifier:
    return ConsistencyVerifier()


@pytest.fixture
def valid_trace() -> AgentTrace:
    steps = [
        TraceStep(0, "tool_call:search", "found results", "success"),
        TraceStep(1, "tool_call:read", "read content", "success"),
        TraceStep(2, "tool_call:write", "wrote output", "success"),
    ]
    return AgentTrace("trace-001", "test-agent", "do stuff", steps, created_at=1000.0)


# ── VerificationResult ────────────────────────────────────────────────────────


def test_verification_result_id_is_content_addressed() -> None:
    r1 = VerificationResult("tid", "verified", ["a"], [], None, 100.0)
    r2 = VerificationResult("tid", "verified", ["a"], [], None, 100.0)
    assert r1.id == r2.id


def test_verification_result_to_dict_has_all_keys() -> None:
    r = VerificationResult("tid", "verified", ["check1"], [], None, 100.0)
    d = r.to_dict()
    expected_keys = (
        "id",
        "trace_id",
        "verdict",
        "checks_passed",
        "checks_failed",
        "error",
        "timestamp",
    )
    for key in expected_keys:
        assert key in d


def test_verification_result_from_dict_roundtrip() -> None:
    r = VerificationResult("tid", "verified", ["check1"], ["check2"], "err", 100.0)
    d = r.to_dict()
    r2 = VerificationResult.from_dict(d)
    assert r2.trace_id == r.trace_id
    assert r2.verdict == r.verdict
    assert r2.checks_passed == r.checks_passed
    assert r2.checks_failed == r.checks_failed


def test_verification_result_repr() -> None:
    r = VerificationResult("tid", "verified", [], [], None, 100.0)
    assert "VerificationResult" in repr(r)
    assert "verified" in repr(r)


# ── ConsistencyVerifier — happy path ─────────────────────────────────────────


def test_verify_valid_trace_returns_verified(
    verifier: ConsistencyVerifier, valid_trace: AgentTrace
) -> None:
    result = verifier.verify(valid_trace)
    assert result.verdict == "verified"
    assert not result.checks_failed


def test_verify_valid_trace_all_checks_pass(
    verifier: ConsistencyVerifier, valid_trace: AgentTrace
) -> None:
    result = verifier.verify(valid_trace)
    assert "hash_chain_integrity" in result.checks_passed
    assert "merkle_root_valid" in result.checks_passed
    assert "step_indices_monotonic" in result.checks_passed
    assert "no_duplicate_step_ids" in result.checks_passed
    assert "trace_id_valid" in result.checks_passed


def test_verify_empty_trace(verifier: ConsistencyVerifier) -> None:
    trace = AgentTrace("tid", "agent", "task", [], created_at=0.0)
    result = verifier.verify(trace)
    assert result.verdict == "verified"


def test_verify_single_step_trace(verifier: ConsistencyVerifier) -> None:
    steps = [TraceStep(0, "action", "obs", "success")]
    trace = AgentTrace("tid", "agent", "task", steps, created_at=0.0)
    result = verifier.verify(trace)
    assert result.verdict == "verified"
    assert steps[0].parent_id is None


# ── ConsistencyVerifier — tampered hash chain ─────────────────────────────────


def test_verify_detects_broken_hash_chain(verifier: ConsistencyVerifier) -> None:
    """Manually break the parent_id chain."""
    steps = [
        TraceStep(0, "action_a", "obs_a", "success"),
        TraceStep(1, "action_b", "obs_b", "success"),
    ]
    trace = AgentTrace("tid", "agent", "task", steps, created_at=0.0)
    # Tamper: break the chain
    trace.steps[1].parent_id = "tampered_value"
    result = verifier.verify(trace)
    assert result.verdict == "tampered"
    assert "hash_chain_integrity" in result.checks_failed


def test_verify_detects_wrong_merkle_root(verifier: ConsistencyVerifier) -> None:
    """Manually corrupt the merkle_root."""
    steps = [TraceStep(0, "action", "obs", "success")]
    trace = AgentTrace("tid", "agent", "task", steps, created_at=0.0)
    trace.merkle_root = "0000000000000000"
    result = verifier.verify(trace)
    assert result.verdict == "tampered"
    assert "merkle_root_valid" in result.checks_failed


# ── ConsistencyVerifier — non-monotonic indices ───────────────────────────────


def test_verify_detects_non_monotonic_indices(verifier: ConsistencyVerifier) -> None:
    """Steps with non-sequential indices should fail."""
    steps = [
        TraceStep(0, "action_a", "obs_a", "success"),
        TraceStep(5, "action_b", "obs_b", "success"),  # gap
    ]
    # Build trace normally (chain is valid), then corrupt step_index
    trace = AgentTrace("tid", "agent", "task", steps, created_at=0.0)
    # Actually steps are [0,5] — let's manually set indices after creation
    result = verifier.verify(trace)
    # step indices [0, 5] are not monotonic +1
    assert "step_indices_monotonic" in result.checks_failed


def test_verify_detects_first_index_not_zero(verifier: ConsistencyVerifier) -> None:
    steps = [TraceStep(1, "action", "obs", "success")]
    trace = AgentTrace("tid", "agent", "task", steps, created_at=0.0)
    # step_index starts at 1 not 0
    result = verifier.verify(trace)
    assert "step_indices_monotonic" in result.checks_failed


# ── ConsistencyVerifier — duplicate IDs ──────────────────────────────────────


def test_verify_detects_duplicate_step_ids(verifier: ConsistencyVerifier) -> None:
    """Two steps with same content will have same id — that's a duplicate."""
    step_a = TraceStep(0, "same_action", "same_obs", "success")
    step_b = TraceStep(1, "same_action", "same_obs", "success")
    # They have the same id because same content (different step_index means different id)
    # To actually get duplicates, we need same step_index too
    # Let's directly set the ids to be equal
    trace = AgentTrace("tid", "agent", "task", [step_a, step_b], created_at=0.0)
    # Override one step's id to match the other
    trace.steps[1].id = trace.steps[0].id
    result = verifier.verify(trace)
    assert "no_duplicate_step_ids" in result.checks_failed


# ── ConsistencyVerifier — trace id mismatch ──────────────────────────────────


def test_verify_detects_invalid_trace_id(verifier: ConsistencyVerifier) -> None:
    steps = [TraceStep(0, "action", "obs", "success")]
    trace = AgentTrace("tid", "agent", "task", steps, created_at=0.0)
    trace.id = "tampered_trace_id"
    result = verifier.verify(trace)
    assert "trace_id_valid" in result.checks_failed


# ── ConsistencyVerifier — result metadata ────────────────────────────────────


def test_verify_result_has_trace_id(verifier: ConsistencyVerifier, valid_trace: AgentTrace) -> None:
    result = verifier.verify(valid_trace)
    assert result.trace_id == "trace-001"


def test_verify_result_has_timestamp(
    verifier: ConsistencyVerifier, valid_trace: AgentTrace
) -> None:
    result = verifier.verify(valid_trace)
    assert result.timestamp > 0


def test_verify_result_error_is_none_for_valid_trace(
    verifier: ConsistencyVerifier, valid_trace: AgentTrace
) -> None:
    result = verifier.verify(valid_trace)
    assert result.error is None
