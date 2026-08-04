"""Closed-loop reader/gate for notarize (Non-Ornament L1).

Who reads the output?
  CI, eagle-eyes ``dogfood_verify``, L4/L5 verifiers that must act on
  tamper or empty traces — never write-only logging.

What outcome changes?
  Structured ``GateOutcome`` with ``exit_code`` for ``sys.exit``.
  Empty traces and load errors are ``FAIL_LOUD`` (exit 2), never silent pass.

Note:
  :class:`~notarize.verifier.ConsistencyVerifier` treats empty traces as
  ``verified`` (no chain to break). This gate intentionally rejects empty
  traces so closed-loop dogfood cannot rubber-stamp "no work done".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notarize.trace import AgentTrace
from notarize.verifier import ConsistencyVerifier, VerificationResult


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty or unusable traces."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of a notarize trace.

    Attributes:
        ok: True only when verification would let a pipeline continue.
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Human-readable explanation (always non-empty).
        exit_code: 0 for PASS, 1 for FAIL (tamper/invalid), 2 for FAIL_LOUD.
        verification: Underlying :class:`VerificationResult` when scoring ran.
        trace_id: Trace identifier when available.
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    verification: VerificationResult | None = None
    trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise for JSON reports (eagle-eyes dogfood, CI artifacts)."""
        payload: dict[str, Any] = {
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "trace_id": self.trace_id,
            "verification": None,
        }
        if self.verification is not None:
            payload["verification"] = self.verification.to_dict()
        return payload


def _fail_loud(reason: str, trace_id: str | None = None) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        verification=None,
        trace_id=trace_id,
    )


def _load_trace(source: AgentTrace | str | Path) -> AgentTrace:
    if isinstance(source, AgentTrace):
        return source
    path = Path(source)
    if not path.is_file():
        raise ClosedLoopError(f"trace file not found: {path}")
    # Prefer store-style loaders if present on AgentTrace
    if hasattr(AgentTrace, "load"):
        return AgentTrace.load(path)  # type: ignore[attr-defined]
    import json

    data = json.loads(path.read_text())
    if hasattr(AgentTrace, "from_dict"):
        return AgentTrace.from_dict(data)  # type: ignore[attr-defined]
    raise ClosedLoopError("cannot load trace: no AgentTrace.load/from_dict")


def gate_trace(
    trace: AgentTrace | str | Path,
    *,
    verifier: ConsistencyVerifier | None = None,
) -> GateOutcome:
    """Read one trace, verify hash-chain integrity, fail loudly on empty/wrong.

    Args:
        trace: :class:`AgentTrace` or path to a serialised trace.
        verifier: Optional verifier instance (defaults to a new one).

    Returns:
        :class:`GateOutcome` — callers should ``sys.exit(outcome.exit_code)``.
    """
    try:
        t = _load_trace(trace)
    except ClosedLoopError as exc:
        return _fail_loud(str(exc))
    except Exception as exc:  # noqa: BLE001 — surface load errors as FAIL_LOUD
        return _fail_loud(f"trace load failed: {exc.__class__.__name__}: {exc}")

    tid = getattr(t, "trace_id", None) or getattr(t, "id", None)

    steps = getattr(t, "steps", None)
    if steps is None:
        return _fail_loud("trace has no steps attribute", tid)
    if len(steps) == 0:
        return _fail_loud("empty trace — write-only empty log is ornament", tid)

    v = verifier or ConsistencyVerifier()
    try:
        result = v.verify(t)
    except Exception as exc:  # noqa: BLE001
        return _fail_loud(f"verify raised: {exc.__class__.__name__}: {exc}", tid)

    if result.verdict in {"verified", "consistent"}:
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason=f"verdict={result.verdict} checks_passed={len(result.checks_passed)}",
            exit_code=0,
            verification=result,
            trace_id=tid,
        )

    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=(
            f"verdict={result.verdict} failed={result.checks_failed} "
            f"error={result.error!r}"
        ),
        exit_code=1,
        verification=result,
        trace_id=tid,
    )


def assert_trace_verified(
    trace: AgentTrace | str | Path,
    **kwargs: Any,
) -> GateOutcome:
    """Gate a trace and raise :class:`ClosedLoopError` unless outcome is ok."""
    outcome = gate_trace(trace, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
