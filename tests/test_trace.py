"""Tests for TraceStep and AgentTrace from notarize.trace."""

from __future__ import annotations

import time

from notarize.trace import AgentTrace, TraceStep, _sha16

# ── _sha16 helper ─────────────────────────────────────────────────────────────


def test_sha16_returns_16_chars() -> None:
    result = _sha16("hello")
    assert len(result) == 16


def test_sha16_deterministic() -> None:
    assert _sha16("abc") == _sha16("abc")


def test_sha16_different_inputs() -> None:
    assert _sha16("abc") != _sha16("def")


# ── TraceStep ─────────────────────────────────────────────────────────────────


def test_tracestep_id_is_content_addressed() -> None:
    s1 = TraceStep(0, "tool_call:search", "result A", "success")
    s2 = TraceStep(0, "tool_call:search", "result A", "success")
    assert s1.id == s2.id


def test_tracestep_different_content_different_id() -> None:
    s1 = TraceStep(0, "tool_call:search", "result A", "success")
    s2 = TraceStep(0, "tool_call:read", "result A", "success")
    assert s1.id != s2.id


def test_tracestep_id_length() -> None:
    s = TraceStep(0, "action", "obs", "result")
    assert len(s.id) == 16


def test_tracestep_to_dict_has_all_keys() -> None:
    s = TraceStep(0, "action", "obs", "success", tool_name="search", timestamp=1000.0)
    d = s.to_dict()
    expected_keys = (
        "step_index",
        "action",
        "observation",
        "result",
        "tool_name",
        "timestamp",
        "id",
        "parent_id",
    )
    for key in expected_keys:
        assert key in d


def test_tracestep_to_dict_values() -> None:
    s = TraceStep(2, "tool_call:search", "found it", "success", tool_name="search", timestamp=999.0)
    d = s.to_dict()
    assert d["step_index"] == 2
    assert d["action"] == "tool_call:search"
    assert d["observation"] == "found it"
    assert d["result"] == "success"
    assert d["tool_name"] == "search"
    assert d["timestamp"] == 999.0


def test_tracestep_from_dict_roundtrip() -> None:
    s = TraceStep(1, "tool_call:read", "read file", "success", tool_name="read", timestamp=100.0)
    d = s.to_dict()
    s2 = TraceStep.from_dict(d)
    assert s2.id == s.id
    assert s2.step_index == s.step_index
    assert s2.action == s.action
    assert s2.observation == s.observation
    assert s2.result == s.result
    assert s2.tool_name == s.tool_name


def test_tracestep_from_dict_parent_id_preserved() -> None:
    s = TraceStep(1, "action", "obs", "result")
    s.parent_id = "abc123def456ab12"
    d = s.to_dict()
    s2 = TraceStep.from_dict(d)
    assert s2.parent_id == "abc123def456ab12"


def test_tracestep_default_tool_name() -> None:
    s = TraceStep(0, "action", "obs", "result")
    assert s.tool_name == ""


def test_tracestep_default_timestamp_is_recent() -> None:
    before = time.time()
    s = TraceStep(0, "action", "obs", "result")
    after = time.time()
    assert before <= s.timestamp <= after


def test_tracestep_repr() -> None:
    s = TraceStep(0, "tool_call:search", "obs", "success")
    r = repr(s)
    assert "TraceStep" in r
    assert "tool_call:search" in r


# ── AgentTrace ────────────────────────────────────────────────────────────────


def test_agenttrace_builds_hash_chain(sample_trace: AgentTrace) -> None:
    """First step has parent_id=None, subsequent steps point to previous."""
    steps = sample_trace.steps
    assert steps[0].parent_id is None
    assert steps[1].parent_id == steps[0].id
    assert steps[2].parent_id == steps[1].id


def test_agenttrace_merkle_root_computed(sample_trace: AgentTrace) -> None:
    assert len(sample_trace.merkle_root) == 16


def test_agenttrace_id_computed(sample_trace: AgentTrace) -> None:
    assert len(sample_trace.id) == 16


def test_agenttrace_id_deterministic() -> None:
    steps1 = [TraceStep(0, "action", "obs", "ok")]
    steps2 = [TraceStep(0, "action", "obs", "ok")]
    t1 = AgentTrace("tid", "agent", "task", steps1, created_at=0.0)
    t2 = AgentTrace("tid", "agent", "task", steps2, created_at=0.0)
    assert t1.id == t2.id
    assert t1.merkle_root == t2.merkle_root


def test_agenttrace_empty_steps() -> None:
    t = AgentTrace("tid", "agent", "task", [], created_at=0.0)
    assert t.merkle_root  # not empty
    assert t.id


def test_agenttrace_to_dict_has_all_keys(sample_trace: AgentTrace) -> None:
    d = sample_trace.to_dict()
    for key in ("trace_id", "agent_name", "task", "steps", "merkle_root", "created_at", "id"):
        assert key in d


def test_agenttrace_to_dict_steps_count(sample_trace: AgentTrace) -> None:
    d = sample_trace.to_dict()
    assert len(d["steps"]) == 3


def test_agenttrace_from_dict_roundtrip(sample_trace: AgentTrace) -> None:
    d = sample_trace.to_dict()
    t2 = AgentTrace.from_dict(d)
    assert t2.trace_id == sample_trace.trace_id
    assert t2.agent_name == sample_trace.agent_name
    assert t2.task == sample_trace.task
    assert len(t2.steps) == len(sample_trace.steps)
    # After from_dict, __post_init__ re-runs so IDs should match
    assert t2.merkle_root == sample_trace.merkle_root


def test_agenttrace_from_dict_preserves_trace_id(sample_trace: AgentTrace) -> None:
    d = sample_trace.to_dict()
    t2 = AgentTrace.from_dict(d)
    assert t2.trace_id == "trace-001"


def test_agenttrace_repr(sample_trace: AgentTrace) -> None:
    r = repr(sample_trace)
    assert "AgentTrace" in r
    assert "trace-001" in r


def test_agenttrace_different_tasks_have_different_ids() -> None:
    t1 = AgentTrace("tid", "agent", "task A", [], created_at=0.0)
    t2 = AgentTrace("tid", "agent", "task B", [], created_at=0.0)
    assert t1.id != t2.id


def test_agenttrace_merkle_root_changes_with_steps() -> None:
    t1 = AgentTrace("tid", "agent", "task", [TraceStep(0, "a", "b", "c")], created_at=0.0)
    t2 = AgentTrace("tid", "agent", "task", [], created_at=0.0)
    assert t1.merkle_root != t2.merkle_root
