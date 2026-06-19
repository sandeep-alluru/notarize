"""Tests for notarize.timeline."""

from __future__ import annotations

import csv
import io
import json

import pytest

from notarize.timeline import to_compliance_report, to_csv, to_timeline_json
from notarize.trace import AgentTrace, TraceStep


def _make_trace(trace_id: str = "t-001", n_steps: int = 3) -> AgentTrace:
    steps = [
        TraceStep(
            step_index=i,
            action=f"action_{i}",
            observation=f"observation_{i}",
            result="success",
            tool_name=f"tool_{i}",
            timestamp=float(1000 + i),
        )
        for i in range(n_steps)
    ]
    return AgentTrace(
        trace_id=trace_id,
        agent_name="test-agent",
        task="do stuff",
        steps=steps,
        created_at=1000.0,
    )


# ---------------------------------------------------------------------------
# to_csv
# ---------------------------------------------------------------------------


def test_to_csv_columns(sample_trace: AgentTrace) -> None:
    """CSV should have the required header columns."""
    csv_str = to_csv(sample_trace)
    reader = csv.reader(io.StringIO(csv_str))
    header = next(reader)
    assert header == ["step_index", "action", "input_summary", "output_summary", "duration_ms", "timestamp"]


def test_to_csv_row_count(sample_trace: AgentTrace) -> None:
    """CSV should have one row per step plus the header."""
    csv_str = to_csv(sample_trace)
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == len(sample_trace.steps) + 1  # +1 for header


def test_to_csv_first_step_duration_zero(sample_trace: AgentTrace) -> None:
    """First step should have duration_ms == 0.0."""
    csv_str = to_csv(sample_trace)
    reader = csv.reader(io.StringIO(csv_str))
    next(reader)  # skip header
    first_row = next(reader)
    assert float(first_row[4]) == 0.0


def test_to_csv_empty_trace() -> None:
    """Empty trace → only the header row."""
    trace = _make_trace(n_steps=0)
    csv_str = to_csv(trace)
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0][0] == "step_index"


def test_to_csv_input_summary_truncated() -> None:
    """input_summary (observation) should be truncated to 80 chars."""
    steps = [
        TraceStep(
            step_index=0,
            action="act",
            observation="x" * 200,
            result="ok",
            timestamp=1000.0,
        )
    ]
    trace = AgentTrace(trace_id="t", agent_name="a", task="task", steps=steps)
    csv_str = to_csv(trace)
    reader = csv.reader(io.StringIO(csv_str))
    next(reader)
    row = next(reader)
    assert len(row[2]) == 80  # input_summary


# ---------------------------------------------------------------------------
# to_timeline_json
# ---------------------------------------------------------------------------


def test_to_timeline_json_valid_json(sample_trace: AgentTrace) -> None:
    """Output should be valid JSON."""
    result = to_timeline_json(sample_trace)
    parsed = json.loads(result)
    assert isinstance(parsed, list)


def test_to_timeline_json_length(sample_trace: AgentTrace) -> None:
    """Array should have one entry per step."""
    parsed = json.loads(to_timeline_json(sample_trace))
    assert len(parsed) == len(sample_trace.steps)


def test_to_timeline_json_fields(sample_trace: AgentTrace) -> None:
    """Each element should have the required keys."""
    parsed = json.loads(to_timeline_json(sample_trace))
    required = {"step_index", "action", "tool_name", "start_time", "duration_ms", "status", "id"}
    for element in parsed:
        assert required <= element.keys()


def test_to_timeline_json_last_step_duration_zero(sample_trace: AgentTrace) -> None:
    """Last step should have duration_ms == 0."""
    parsed = json.loads(to_timeline_json(sample_trace))
    assert parsed[-1]["duration_ms"] == 0.0


def test_to_timeline_json_empty_trace() -> None:
    """Empty trace → empty JSON array."""
    trace = _make_trace(n_steps=0)
    result = json.loads(to_timeline_json(trace))
    assert result == []


# ---------------------------------------------------------------------------
# to_compliance_report
# ---------------------------------------------------------------------------


def test_compliance_report_soc2(sample_trace: AgentTrace) -> None:
    """SOC2 report should mention key headings."""
    report = to_compliance_report(sample_trace, standard="SOC2")
    assert "SOC2" in report
    assert sample_trace.trace_id in report
    assert "Availability" in report
    assert "Confidentiality" in report
    assert "Processing Integrity" in report
    assert sample_trace.merkle_root in report


def test_compliance_report_hipaa(sample_trace: AgentTrace) -> None:
    """HIPAA report should mention PHI handling."""
    report = to_compliance_report(sample_trace, standard="HIPAA")
    assert "HIPAA" in report
    assert "PHI" in report
    assert "Access Controls" in report


def test_compliance_report_gdpr(sample_trace: AgentTrace) -> None:
    """GDPR report should mention data minimisation."""
    report = to_compliance_report(sample_trace, standard="GDPR")
    assert "GDPR" in report
    assert "minimis" in report.lower()
    assert "Retention" in report


def test_compliance_report_step_table(sample_trace: AgentTrace) -> None:
    """Report should contain a table with all steps."""
    report = to_compliance_report(sample_trace)
    for step in sample_trace.steps:
        assert step.action in report


def test_compliance_report_unknown_standard(sample_trace: AgentTrace) -> None:
    """Unknown standard should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown compliance standard"):
        to_compliance_report(sample_trace, standard="ISO27001")


def test_compliance_report_default_standard(sample_trace: AgentTrace) -> None:
    """Default standard is SOC2."""
    report = to_compliance_report(sample_trace)
    assert "SOC2" in report
