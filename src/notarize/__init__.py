"""notarize — Canonical trace format and verifier for agent execution attestation"""

from __future__ import annotations

import importlib.metadata

from notarize.scrubber import PrivacyScrubber, ScrubResult
from notarize.store import TraceStore
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier, VerificationResult

__version__ = importlib.metadata.version("notarize")

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
