"""Shared pytest fixtures for notarize tests."""

from __future__ import annotations

import pytest

from notarize.trace import AgentTrace, TraceStep


@pytest.fixture
def sample_steps() -> list[TraceStep]:
    """Return a list of 3 sample TraceStep objects."""
    return [
        TraceStep(
            step_index=0,
            action="tool_call:search",
            observation="Found 5 results",
            result="success",
            tool_name="search",
            timestamp=1000.0,
        ),
        TraceStep(
            step_index=1,
            action="tool_call:read",
            observation="Read file content",
            result="success",
            tool_name="read",
            timestamp=1001.0,
        ),
        TraceStep(
            step_index=2,
            action="tool_call:write",
            observation="Wrote to output",
            result="success",
            tool_name="write",
            timestamp=1002.0,
        ),
    ]


@pytest.fixture
def sample_trace(sample_steps: list[TraceStep]) -> AgentTrace:
    """Return a sample AgentTrace with 3 steps."""
    return AgentTrace(
        trace_id="trace-001",
        agent_name="test-agent",
        task="Search and process files",
        steps=sample_steps,
        created_at=1000.0,
    )
