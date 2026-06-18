"""ConsistencyVerifier for verifying the internal consistency of AgentTrace objects."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from notarize.trace import AgentTrace, _sha16


@dataclass
class VerificationResult:
    """Result of verifying an AgentTrace.

    Attributes:
        trace_id: The trace_id of the verified trace.
        verdict: One of "verified", "consistent", "tampered", "invalid".
        checks_passed: List of check names that passed.
        checks_failed: List of check names that failed.
        error: Optional error message if an exception occurred.
        timestamp: Unix timestamp of the verification.
        id: Content-addressed identifier of this result.
    """

    trace_id: str
    verdict: str
    checks_passed: list[str]
    checks_failed: list[str]
    error: str | None
    timestamp: float
    id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = (
            f"{self.trace_id}|{self.verdict}|"
            f"{','.join(sorted(self.checks_passed))}|"
            f"{','.join(sorted(self.checks_failed))}|"
            f"{self.error or ''}|{self.timestamp}"
        )
        self.id = _sha16(payload)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "trace_id": self.trace_id,
            "verdict": self.verdict,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VerificationResult:
        """Deserialize from a dict produced by to_dict()."""
        result = cls(
            trace_id=d["trace_id"],
            verdict=d["verdict"],
            checks_passed=d.get("checks_passed", []),
            checks_failed=d.get("checks_failed", []),
            error=d.get("error"),
            timestamp=d.get("timestamp", 0.0),
        )
        return result

    def __repr__(self) -> str:
        return f"VerificationResult({self.id!r}: {self.trace_id!r} -> {self.verdict!r})"


class ConsistencyVerifier:
    """Verifies the internal consistency of an AgentTrace.

    Performs the following checks:
    1. Hash chain integrity: each step.parent_id == previous step.id
    2. Merkle root matches recomputed value
    3. Step indices are monotonically increasing from 0
    4. No duplicate step IDs
    5. Trace ID matches stored trace.id
    """

    def verify(self, trace: AgentTrace) -> VerificationResult:
        """Verify the internal consistency of an AgentTrace.

        Args:
            trace: The AgentTrace to verify.

        Returns:
            A VerificationResult with verdict and check details.
        """
        checks_passed: list[str] = []
        checks_failed: list[str] = []
        error: str | None = None

        try:
            # Check 1: Hash chain integrity
            chain_ok = True
            for i, step in enumerate(trace.steps):
                if i == 0:
                    if step.parent_id is not None:
                        chain_ok = False
                        break
                else:
                    expected_parent = trace.steps[i - 1].id
                    if step.parent_id != expected_parent:
                        chain_ok = False
                        break

            if chain_ok:
                checks_passed.append("hash_chain_integrity")
            else:
                checks_failed.append("hash_chain_integrity")

            # Check 2: Merkle root matches recomputed value
            step_ids = sorted(s.id for s in trace.steps)
            computed_root = _sha16("|".join(step_ids)) if step_ids else _sha16("")
            if computed_root == trace.merkle_root:
                checks_passed.append("merkle_root_valid")
            else:
                checks_failed.append("merkle_root_valid")

            # Check 3: Step indices are monotonically increasing from 0
            indices_ok = True
            if trace.steps:
                if trace.steps[0].step_index != 0:
                    indices_ok = False
                else:
                    for i in range(1, len(trace.steps)):
                        if trace.steps[i].step_index != trace.steps[i - 1].step_index + 1:
                            indices_ok = False
                            break

            if indices_ok:
                checks_passed.append("step_indices_monotonic")
            else:
                checks_failed.append("step_indices_monotonic")

            # Check 4: No duplicate step IDs
            step_id_set = [s.id for s in trace.steps]
            if len(step_id_set) == len(set(step_id_set)):
                checks_passed.append("no_duplicate_step_ids")
            else:
                checks_failed.append("no_duplicate_step_ids")

            # Check 5: Trace ID matches stored trace.id
            computed_trace_id = _sha16(
                f"{trace.trace_id}|{trace.agent_name}|{trace.task}|{trace.merkle_root}"
            )
            if computed_trace_id == trace.id:
                checks_passed.append("trace_id_valid")
            else:
                checks_failed.append("trace_id_valid")

        except Exception as exc:
            error = str(exc)
            checks_failed.append("unexpected_error")

        # Determine verdict
        if error:
            verdict = "invalid"
        elif not checks_failed:
            verdict = "verified"
        elif (
            "hash_chain_integrity" in checks_failed
            or "merkle_root_valid" in checks_failed
            or "trace_id_valid" in checks_failed
        ):
            verdict = "tampered"
        else:
            verdict = "consistent"

        return VerificationResult(
            trace_id=trace.trace_id,
            verdict=verdict,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            error=error,
            timestamp=time.time(),
        )
