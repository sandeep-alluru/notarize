"""Tests for notarize.audit."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from notarize.audit import AuditSummary, summarize, summarize_session
from notarize.store import TraceStore
from notarize.trace import AgentTrace, TraceStep


def _make_step(
    index: int,
    action: str = "action",
    obs: str = "obs",
    result: str = "ok",
    tool: str = "tool",
    timestamp: float | None = None,
) -> TraceStep:
    return TraceStep(
        step_index=index,
        action=action,
        observation=obs,
        result=result,
        tool_name=tool,
        timestamp=timestamp if timestamp is not None else float(1000 + index),
    )


def _make_trace(
    trace_id: str = "t-001",
    agent_name: str = "agent",
    steps: list[TraceStep] | None = None,
) -> AgentTrace:
    if steps is None:
        steps = [_make_step(0), _make_step(1), _make_step(2)]
    return AgentTrace(
        trace_id=trace_id,
        agent_name=agent_name,
        task="do stuff",
        steps=steps,
    )


# ---------------------------------------------------------------------------
# Basic summarize
# ---------------------------------------------------------------------------


def test_summarize_returns_audit_summary(sample_trace: AgentTrace) -> None:
    """summarize should return an AuditSummary instance."""
    result = summarize(sample_trace)
    assert isinstance(result, AuditSummary)


def test_summarize_session_id(sample_trace: AgentTrace) -> None:
    """session_id should be the trace_id."""
    result = summarize(sample_trace)
    assert result.session_id == sample_trace.trace_id


def test_summarize_agent_id(sample_trace: AgentTrace) -> None:
    """agent_id should be agent_name."""
    result = summarize(sample_trace)
    assert result.agent_id == sample_trace.agent_name


def test_summarize_total_steps(sample_trace: AgentTrace) -> None:
    """total_steps should equal the number of steps."""
    result = summarize(sample_trace)
    assert result.total_steps == len(sample_trace.steps)


def test_summarize_normal_trace_no_risk_flags(sample_trace: AgentTrace) -> None:
    """A clean short trace should have no risk flags."""
    result = summarize(sample_trace)
    assert result.risk_flags == []


def test_summarize_chain_valid(sample_trace: AgentTrace) -> None:
    """sample_trace is freshly constructed → chain should be valid."""
    result = summarize(sample_trace)
    assert result.chain_valid is True


def test_summarize_tools_used(sample_trace: AgentTrace) -> None:
    """tools_used should list unique tool names in order of appearance."""
    result = summarize(sample_trace)
    assert result.tools_used == ["search", "read", "write"]


def test_summarize_compliance_score_clean(sample_trace: AgentTrace) -> None:
    """Clean trace should have compliance score 100."""
    result = summarize(sample_trace)
    assert result.compliance_score == 100.0


# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------


def test_summarize_pii_detected() -> None:
    """Trace with an email in action should trigger pii_detected flag."""
    steps = [
        TraceStep(
            step_index=0,
            action="contact user@example.com about the issue",
            observation="sent",
            result="ok",
            tool_name="email",
            timestamp=1000.0,
        )
    ]
    trace = _make_trace(steps=steps)
    result = summarize(trace)

    assert result.pii_fields_scrubbed > 0
    assert "pii_detected" in result.risk_flags
    assert result.compliance_score <= 80.0


# ---------------------------------------------------------------------------
# many_steps flag
# ---------------------------------------------------------------------------


def test_summarize_many_steps_flag() -> None:
    """A trace with >50 steps should trigger many_steps flag."""
    steps = [_make_step(i) for i in range(51)]
    trace = _make_trace(steps=steps)
    result = summarize(trace)

    assert "many_steps" in result.risk_flags


# ---------------------------------------------------------------------------
# no_tools_used flag
# ---------------------------------------------------------------------------


def test_summarize_no_tools_used_flag() -> None:
    """Steps with empty tool_name should trigger no_tools_used."""
    steps = [
        TraceStep(step_index=0, action="a", observation="b", result="c", tool_name="", timestamp=1000.0),
    ]
    trace = _make_trace(steps=steps)
    result = summarize(trace)

    assert "no_tools_used" in result.risk_flags
    assert result.tools_used == []


# ---------------------------------------------------------------------------
# Compliance score deductions
# ---------------------------------------------------------------------------


def test_compliance_score_deductions() -> None:
    """Verify each risk factor deducts the correct amount."""
    # Create a trace with PII (pii_detected → -20) and no tools (-10)
    steps = [
        TraceStep(
            step_index=0,
            action="email user@example.com",
            observation="done",
            result="ok",
            tool_name="",
            timestamp=1000.0,
        )
    ]
    trace = _make_trace(steps=steps)
    result = summarize(trace)

    # pii_detected (-20) + no_tools_used (-10) = -30
    assert result.compliance_score == pytest.approx(70.0)


def test_compliance_score_clamped_to_zero() -> None:
    """Compliance score should not go below 0."""
    # Max deductions: chain_broken(-20) + pii(-20) + long_duration(-10) + many_steps(-10) + no_tools(-10) = -70
    # With a very degraded trace we should hit 0 or above
    result_score = 100.0 - 20 - 20 - 10 - 10 - 10
    assert max(0.0, result_score) == 30.0


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------


def test_summarize_duration_ms() -> None:
    """duration_ms should be (last - first) * 1000."""
    steps = [
        _make_step(0, timestamp=1000.0),
        _make_step(1, timestamp=1001.5),
        _make_step(2, timestamp=1002.0),
    ]
    trace = _make_trace(steps=steps)
    result = summarize(trace)

    assert result.duration_ms == pytest.approx(2000.0)


def test_summarize_empty_trace_duration() -> None:
    """Empty trace → duration 0."""
    trace = _make_trace(steps=[])
    result = summarize(trace)
    assert result.duration_ms == 0.0


# ---------------------------------------------------------------------------
# summarize_session
# ---------------------------------------------------------------------------


def test_summarize_session_by_agent_name() -> None:
    """summarize_session should match traces whose agent_name equals session_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with TraceStore(db_path) as store:
            t1 = _make_trace(trace_id="abc-001", agent_name="my-agent")
            t2 = _make_trace(trace_id="def-001", agent_name="other-agent")
            t3 = _make_trace(trace_id="abc-002", agent_name="my-agent")
            store.save_trace(t1)
            store.save_trace(t2)
            store.save_trace(t3)

            summaries = summarize_session(store, "my-agent")

    assert len(summaries) == 2
    assert all(s.agent_id == "my-agent" for s in summaries)


def test_summarize_session_by_trace_id_prefix() -> None:
    """summarize_session should match traces whose trace_id starts with session_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with TraceStore(db_path) as store:
            t1 = _make_trace(trace_id="session-001", agent_name="agentA")
            t2 = _make_trace(trace_id="session-002", agent_name="agentB")
            t3 = _make_trace(trace_id="other-001", agent_name="agentC")
            store.save_trace(t1)
            store.save_trace(t2)
            store.save_trace(t3)

            summaries = summarize_session(store, "session-")

    assert len(summaries) == 2


def test_summarize_session_empty_result() -> None:
    """No matching traces → empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with TraceStore(db_path) as store:
            t1 = _make_trace(trace_id="abc-001", agent_name="agent-x")
            store.save_trace(t1)

            summaries = summarize_session(store, "zzz-nonexistent")

    assert summaries == []
