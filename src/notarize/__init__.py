"""notarize — Canonical trace format and verifier for agent execution attestation"""

from __future__ import annotations

import importlib.metadata

from notarize.audit import AuditSummary, summarize, summarize_session
from notarize.closed_loop import (
    ClosedLoopError,
    GateOutcome,
    assert_no_silent_success,
    assert_trace_verified,
    degraded_step_indices,
    failed_step_indices,
    gate_claimed_success,
    gate_trace,
    step_is_degraded,
    step_is_failed,
)
from notarize.compare import StepComparison, TraceComparison, compare_traces
from notarize.scrubber import PrivacyScrubber, ScrubResult
from notarize.store import TraceStore
from notarize.timeline import to_compliance_report, to_csv, to_timeline_json
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier, VerificationResult

__version__ = importlib.metadata.version("notarize-ai")

__all__ = [
    "AgentTrace",
    "AuditSummary",
    "ClosedLoopError",
    "ConsistencyVerifier",
    "GateOutcome",
    "PrivacyScrubber",
    "ScrubResult",
    "StepComparison",
    "TraceComparison",
    "TraceStep",
    "TraceStore",
    "VerificationResult",
    "__version__",
    "assert_no_silent_success",
    "assert_trace_verified",
    "compare_traces",
    "degraded_step_indices",
    "failed_step_indices",
    "gate_claimed_success",
    "gate_trace",
    "step_is_degraded",
    "step_is_failed",
    "summarize",
    "summarize_session",
    "to_compliance_report",
    "to_csv",
    "to_timeline_json",
]
