"""AuditSummary — aggregate compliance and risk analysis for a trace."""

from __future__ import annotations

from dataclasses import dataclass

from notarize.scrubber import _scrub_text
from notarize.store import TraceStore
from notarize.trace import AgentTrace
from notarize.verifier import ConsistencyVerifier


@dataclass
class AuditSummary:
    session_id: str
    agent_id: str
    total_steps: int
    duration_ms: float
    tools_used: list[str]
    pii_fields_scrubbed: int
    chain_valid: bool
    risk_flags: list[str]
    compliance_score: float  # 0-100


def summarize(trace: AgentTrace) -> AuditSummary:
    """Produce an AuditSummary for a single AgentTrace.

    Args:
        trace: The AgentTrace to analyse.

    Returns:
        An AuditSummary with risk flags and compliance score.
    """
    steps = trace.steps
    total_steps = len(steps)

    # Duration
    if steps and hasattr(steps[0], "timestamp") and hasattr(steps[-1], "timestamp"):
        duration_ms = (steps[-1].timestamp - steps[0].timestamp) * 1000.0
    else:
        duration_ms = 0.0

    # Tools used (unique, in order of first appearance)
    seen: set[str] = set()
    tools_used: list[str] = []
    for step in steps:
        name = step.tool_name
        if name and name not in seen:
            seen.add(name)
            tools_used.append(name)

    # PII count — sum replacements across all text fields in all steps
    pii_fields_scrubbed = 0
    for step in steps:
        for text in (step.action, step.observation, step.result, step.tool_name):
            if text:
                _, count, _ = _scrub_text(text)
                pii_fields_scrubbed += count

    # Chain validity
    result = ConsistencyVerifier().verify(trace)
    chain_valid = result.verdict in ("verified", "consistent")

    # Risk flags
    risk_flags: list[str] = []
    if duration_ms > 300_000:
        risk_flags.append("long_duration")
    if total_steps > 50:
        risk_flags.append("many_steps")
    if pii_fields_scrubbed > 0:
        risk_flags.append("pii_detected")
    if not chain_valid:
        risk_flags.append("chain_broken")
    if not tools_used:
        risk_flags.append("no_tools_used")

    # Compliance score
    score = 100.0
    if "chain_broken" in risk_flags:
        score -= 20
    if "pii_detected" in risk_flags:
        score -= 20
    if "long_duration" in risk_flags:
        score -= 10
    if "many_steps" in risk_flags:
        score -= 10
    if "no_tools_used" in risk_flags:
        score -= 10
    compliance_score = max(0.0, min(100.0, score))

    return AuditSummary(
        session_id=trace.trace_id,
        agent_id=trace.agent_name,
        total_steps=total_steps,
        duration_ms=duration_ms,
        tools_used=tools_used,
        pii_fields_scrubbed=pii_fields_scrubbed,
        chain_valid=chain_valid,
        risk_flags=risk_flags,
        compliance_score=compliance_score,
    )


def summarize_session(store: TraceStore, session_id: str) -> list[AuditSummary]:
    """Return AuditSummary objects for all traces belonging to a session.

    A trace belongs to the session if its trace_id starts with session_id OR
    its agent_name equals session_id.

    Args:
        store: The TraceStore to query.
        session_id: A session prefix or agent name to match.

    Returns:
        A list of AuditSummary objects, one per matching trace.
    """
    all_traces = store.list_traces()
    matching = [
        t for t in all_traces if t.trace_id.startswith(session_id) or t.agent_name == session_id
    ]
    return [summarize(t) for t in matching]
