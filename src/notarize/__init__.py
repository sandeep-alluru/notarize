"""notarize - Canonical trace format and verifier for agent execution attestation"""

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
from notarize.trace_compile import (
    CompiledWorkflow,
    ToolInvocation,
    WorkflowEdge,
    assert_compiled_workflow_ok,
    compile_trace_workflow,
    gate_compiled_workflow,
    hard_edges_missing_evidence,
)
from notarize.triage_audit import (
    PairedTriageCase,
    TriageAuditReport,
    TriageStage,
    analyze_triage_pipeline,
    assert_triage_audit_ok,
    gate_triage_audit,
)
from notarize.verifier import ConsistencyVerifier, VerificationResult

__version__ = importlib.metadata.version("notarize-ai")

__all__ = [
    "AgentTrace",
    "AuditSummary",
    "ClosedLoopError",
    "CompiledWorkflow",
    "ConsistencyVerifier",
    "GateOutcome",
    "PairedTriageCase",
    "PrivacyScrubber",
    "ScrubResult",
    "StepComparison",
    "ToolInvocation",
    "TraceComparison",
    "TraceStep",
    "TraceStore",
    "TriageAuditReport",
    "TriageStage",
    "VerificationResult",
    "WorkflowEdge",
    "__version__",
    "analyze_triage_pipeline",
    "assert_compiled_workflow_ok",
    "assert_no_silent_success",
    "assert_trace_verified",
    "assert_triage_audit_ok",
    "compare_traces",
    "compile_trace_workflow",
    "degraded_step_indices",
    "failed_step_indices",
    "gate_claimed_success",
    "gate_compiled_workflow",
    "gate_trace",
    "gate_triage_audit",
    "hard_edges_missing_evidence",
    "step_is_degraded",
    "step_is_failed",
    "summarize",
    "summarize_session",
    "to_compliance_report",
    "to_csv",
    "to_timeline_json",
]
