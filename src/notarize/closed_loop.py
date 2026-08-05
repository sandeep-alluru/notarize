"""Closed-loop reader/gate for notarize (Non-Ornament L1).

Who reads the output?
  CI, eagle-eyes ``dogfood_verify``, L4/L5 verifiers that must act on
  tamper or empty traces — never write-only logging.

What outcome changes?
  Structured ``GateOutcome`` with ``exit_code`` for ``sys.exit``.
  Empty traces and load errors are ``FAIL_LOUD`` (exit 2), never silent pass.

SILENT-SUCCESS (farm / Foundry assemble class):
  A process that exits 0 or claims ``success=True`` while the execution
  trace contains failed or *degraded* steps is a silent success. Hash-chain
  integrity alone is not enough — integrators must refuse degraded outcomes.

Note:
  :class:`~notarize.verifier.ConsistencyVerifier` treats empty traces as
  ``verified`` (no chain to break). This gate intentionally rejects empty
  traces so closed-loop dogfood cannot rubber-stamp "no work done".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier, VerificationResult

# Step.result tokens that mean the step did not fully succeed.
_FAILURE_RESULTS: frozenset[str] = frozenset(
    {
        "error",
        "fail",
        "failed",
        "failure",
        "exception",
        "timeout",
        "aborted",
        "cancelled",
        "canceled",
        "denied",
        "refused",
    }
)

# Soft-failure / partial-completion tokens (assemble-exits-0-degraded class).
_DEGRADED_RESULTS: frozenset[str] = frozenset(
    {
        "degraded",
        "partial",
        "incomplete",
        "skipped",
        "warning",
        "warn",
        "soft_fail",
        "best_effort",
    }
)

_DEGRADED_TEXT = re.compile(
    r"\b(degraded|partial(?:ly)?\s+complete|incomplete|best[- ]effort|"
    r"soft[- ]fail|with\s+errors|missing\s+artifacts?)\b",
    re.IGNORECASE,
)


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty or unusable traces."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of a notarize trace.

    Attributes:
        ok: True only when verification would let a pipeline continue.
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Human-readable explanation (always non-empty).
        exit_code: 0 for PASS, 1 for FAIL (tamper/invalid/degraded), 2 for FAIL_LOUD.
        verification: Underlying :class:`VerificationResult` when scoring ran.
        trace_id: Trace identifier when available.
        failed_step_indices: Steps with hard-failure results.
        degraded_step_indices: Steps with degraded/partial results.
        silent_success: True when claimed success conflicts with step outcomes.
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    verification: VerificationResult | None = None
    trace_id: str | None = None
    failed_step_indices: tuple[int, ...] = ()
    degraded_step_indices: tuple[int, ...] = ()
    silent_success: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialise for JSON reports (eagle-eyes dogfood, CI artifacts)."""
        payload: dict[str, Any] = {
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "trace_id": self.trace_id,
            "failed_step_indices": list(self.failed_step_indices),
            "degraded_step_indices": list(self.degraded_step_indices),
            "silent_success": self.silent_success,
            "verification": None,
        }
        if self.verification is not None:
            payload["verification"] = self.verification.to_dict()
        return payload


def _norm_result(result: str) -> str:
    return (result or "").strip().lower().replace("-", "_").replace(" ", "_")


def step_is_failed(step: TraceStep) -> bool:
    """True when the step records a hard failure result."""
    r = _norm_result(step.result)
    if r in _FAILURE_RESULTS:
        return True
    # "error:timeout", "failed:disk"
    head = r.split(":", 1)[0]
    return head in _FAILURE_RESULTS


def step_is_degraded(step: TraceStep) -> bool:
    """True when the step is partial/degraded (not a clean success)."""
    if step_is_failed(step):
        return False
    r = _norm_result(step.result)
    if r in _DEGRADED_RESULTS:
        return True
    head = r.split(":", 1)[0]
    if head in _DEGRADED_RESULTS:
        return True
    blob = f"{step.result} {step.observation} {step.action}"
    return bool(_DEGRADED_TEXT.search(blob))


def failed_step_indices(trace: AgentTrace) -> list[int]:
    return [s.step_index for s in trace.steps if step_is_failed(s)]


def degraded_step_indices(trace: AgentTrace) -> list[int]:
    return [s.step_index for s in trace.steps if step_is_degraded(s)]


def _fail_loud(
    reason: str,
    trace_id: str | None = None,
    *,
    failed: Iterable[int] = (),
    degraded: Iterable[int] = (),
    silent_success: bool = False,
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        verification=None,
        trace_id=trace_id,
        failed_step_indices=tuple(failed),
        degraded_step_indices=tuple(degraded),
        silent_success=silent_success,
    )


def _fail(
    reason: str,
    trace_id: str | None = None,
    *,
    verification: VerificationResult | None = None,
    failed: Iterable[int] = (),
    degraded: Iterable[int] = (),
    silent_success: bool = False,
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=reason,
        exit_code=1,
        verification=verification,
        trace_id=trace_id,
        failed_step_indices=tuple(failed),
        degraded_step_indices=tuple(degraded),
        silent_success=silent_success,
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
    refuse_degraded: bool = True,
    refuse_failed_steps: bool = True,
) -> GateOutcome:
    """Read one trace, verify hash-chain integrity, fail loudly on empty/wrong.

    Args:
        trace: :class:`AgentTrace` or path to a serialised trace.
        verifier: Optional verifier instance (defaults to a new one).
        refuse_degraded: If True (default), degraded/partial steps → FAIL
            (SILENT-SUCCESS class — clean chain must not hide soft failure).
        refuse_failed_steps: If True (default), any hard-failure step → FAIL
            even when the chain hashes correctly.

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

    failed_ix = failed_step_indices(t)
    degraded_ix = degraded_step_indices(t)

    v = verifier or ConsistencyVerifier()
    try:
        result = v.verify(t)
    except Exception as exc:  # noqa: BLE001
        return _fail_loud(f"verify raised: {exc.__class__.__name__}: {exc}", tid)

    if result.verdict not in {"verified", "consistent"}:
        return _fail(
            f"verdict={result.verdict} failed={result.checks_failed} "
            f"error={result.error!r}",
            tid,
            verification=result,
            failed=failed_ix,
            degraded=degraded_ix,
        )

    # Chain is intact — still refuse failed / degraded steps (SILENT-SUCCESS).
    if refuse_failed_steps and failed_ix:
        return _fail(
            f"SILENT-SUCCESS: chain verified but failed steps at {failed_ix} "
            f"— refuse success (assemble/exit-0 degraded class)",
            tid,
            verification=result,
            failed=failed_ix,
            degraded=degraded_ix,
            silent_success=True,
        )

    if refuse_degraded and degraded_ix:
        return _fail(
            f"SILENT-SUCCESS: chain verified but degraded steps at {degraded_ix} "
            f"— refuse clean PASS",
            tid,
            verification=result,
            failed=failed_ix,
            degraded=degraded_ix,
            silent_success=True,
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=f"verdict={result.verdict} checks_passed={len(result.checks_passed)}",
        exit_code=0,
        verification=result,
        trace_id=tid,
        failed_step_indices=tuple(failed_ix),
        degraded_step_indices=tuple(degraded_ix),
        silent_success=False,
    )


def gate_claimed_success(
    claimed_ok: bool,
    claimed_exit_code: int,
    trace: AgentTrace | str | Path,
    *,
    verifier: ConsistencyVerifier | None = None,
) -> GateOutcome:
    """Gate a process claim (exit code / success flag) against the real trace.

    SILENT-SUCCESS control for assemble-style pipelines:

    * ``claimed_ok=True`` or ``claimed_exit_code==0`` with failed/degraded
      steps → FAIL (exit 1), never silent pass.
    * Claim already failed → still verify empty/tamper (may be FAIL_LOUD).
    * Clean claim + clean trace → PASS.

    Args:
        claimed_ok: What the process reported (``success`` flag).
        claimed_exit_code: Process exit code (0 = success claim).
        trace: Execution trace to read.
        verifier: Optional consistency verifier.
    """
    claim_success = bool(claimed_ok) or claimed_exit_code == 0

    # Always run integrity + degraded checks; then compare to claim.
    base = gate_trace(
        trace,
        verifier=verifier,
        refuse_degraded=True,
        refuse_failed_steps=True,
    )

    if not claim_success:
        # Process already admitted failure — surface integrity issues first.
        if base.verdict == "FAIL_LOUD":
            return base
        if base.silent_success or base.failed_step_indices or base.degraded_step_indices:
            # Consistent: claim failed and trace shows problems.
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    f"claimed failure (exit={claimed_exit_code}, ok={claimed_ok}) "
                    f"aligned with trace issues: {base.reason}"
                ),
                exit_code=1,
                verification=base.verification,
                trace_id=base.trace_id,
                failed_step_indices=base.failed_step_indices,
                degraded_step_indices=base.degraded_step_indices,
                silent_success=False,
            )
        if not base.ok:
            return base
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=f"claimed failure (exit={claimed_exit_code}) with clean trace",
            exit_code=1,
            verification=base.verification,
            trace_id=base.trace_id,
        )

    # Claimed success — base already fails on silent success / empty / tamper.
    if not base.ok:
        # Escalate reason if claim was success
        if base.silent_success or base.failed_step_indices or base.degraded_step_indices:
            return GateOutcome(
                ok=False,
                verdict=base.verdict if base.verdict == "FAIL_LOUD" else "FAIL",
                reason=(
                    f"SILENT-SUCCESS: claimed success (exit={claimed_exit_code}, "
                    f"ok={claimed_ok}) but {base.reason}"
                ),
                exit_code=base.exit_code if base.verdict == "FAIL_LOUD" else 1,
                verification=base.verification,
                trace_id=base.trace_id,
                failed_step_indices=base.failed_step_indices,
                degraded_step_indices=base.degraded_step_indices,
                silent_success=True,
            )
        return base

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"claimed success matches clean verified trace "
            f"(exit={claimed_exit_code})"
        ),
        exit_code=0,
        verification=base.verification,
        trace_id=base.trace_id,
        silent_success=False,
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


def assert_no_silent_success(
    claimed_ok: bool,
    claimed_exit_code: int,
    trace: AgentTrace | str | Path,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` on SILENT-SUCCESS or other gate failure."""
    outcome = gate_claimed_success(claimed_ok, claimed_exit_code, trace, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
