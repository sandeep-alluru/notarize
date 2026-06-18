"""tracemarket — Canonical trace format and verifier for agent execution attestation"""

from __future__ import annotations

import importlib.metadata

from tracemarket.scrubber import PrivacyScrubber, ScrubResult
from tracemarket.store import TraceStore
from tracemarket.trace import AgentTrace, TraceStep
from tracemarket.verifier import ConsistencyVerifier, VerificationResult

__version__ = importlib.metadata.version("tracemarket")

__all__ = [
    "AgentTrace",
    "ConsistencyVerifier",
    "PrivacyScrubber",
    "ScrubResult",
    "TraceStep",
    "TraceStore",
    "VerificationResult",
    "__version__",
]
