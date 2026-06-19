"""notarize — Canonical trace format and verifier for agent execution attestation"""

from __future__ import annotations

import importlib.metadata

from notarize.audit import AuditSummary, summarize, summarize_session
from notarize.compare import StepComparison, TraceComparison, compare_traces
from notarize.scrubber import PrivacyScrubber, ScrubResult
from notarize.store import TraceStore
from notarize.timeline import to_compliance_report, to_csv, to_timeline_json
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier, VerificationResult

__version__ = importlib.metadata.version("notarize")

__all__ = [
    "AgentTrace",
    "AuditSummary",
    "ConsistencyVerifier",
    "PrivacyScrubber",
    "ScrubResult",
    "StepComparison",
    "TraceComparison",
    "TraceStep",
    "TraceStore",
    "VerificationResult",
    "__version__",
    "compare_traces",
    "summarize",
    "summarize_session",
    "to_compliance_report",
    "to_csv",
    "to_timeline_json",
]
