"""Step-by-step comparison of two AgentTraces."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from notarize.trace import AgentTrace, TraceStep


@dataclass
class StepComparison:
    step_index: int
    status: str  # "match", "changed", "added", "removed"
    baseline_action: str | None
    candidate_action: str | None
    similarity: float  # 0-1


@dataclass
class TraceComparison:
    baseline_id: str
    candidate_id: str
    step_comparisons: list[StepComparison]
    first_divergence: int | None
    similarity_score: float  # 0-1 overall
    verdict: str  # "identical", "minor_drift", "major_divergence"


def _step_text(step: TraceStep) -> str:
    """Concatenate action|observation|result for a step."""
    return f"{step.action}|{step.observation}|{step.result}"


def _similarity(a: str, b: str) -> float:
    """Compute character-level similarity ratio between two strings."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def compare_traces(baseline: AgentTrace, candidate: AgentTrace) -> TraceComparison:
    """Compare two AgentTraces step by step.

    For each step position both traces have in common, compute the similarity
    between the concatenated "action|observation|result" strings.  Steps only
    present in one trace are marked "added" or "removed" with similarity 0.

    Args:
        baseline: The reference AgentTrace.
        candidate: The AgentTrace to compare against the baseline.

    Returns:
        A TraceComparison with per-step breakdowns and an overall verdict.
    """
    baseline_steps = baseline.steps
    candidate_steps = candidate.steps

    # Handle the empty-traces edge case early.
    if not baseline_steps and not candidate_steps:
        return TraceComparison(
            baseline_id=baseline.trace_id,
            candidate_id=candidate.trace_id,
            step_comparisons=[],
            first_divergence=None,
            similarity_score=1.0,
            verdict="identical",
        )

    max_len = max(len(baseline_steps), len(candidate_steps))
    comparisons: list[StepComparison] = []

    for i in range(max_len):
        has_baseline = i < len(baseline_steps)
        has_candidate = i < len(candidate_steps)

        if has_baseline and has_candidate:
            b_text = _step_text(baseline_steps[i])
            c_text = _step_text(candidate_steps[i])
            sim = _similarity(b_text, c_text)
            status = "match" if sim >= 0.95 else "changed"
            comparisons.append(
                StepComparison(
                    step_index=i,
                    status=status,
                    baseline_action=baseline_steps[i].action,
                    candidate_action=candidate_steps[i].action,
                    similarity=sim,
                )
            )
        elif has_baseline:
            comparisons.append(
                StepComparison(
                    step_index=i,
                    status="removed",
                    baseline_action=baseline_steps[i].action,
                    candidate_action=None,
                    similarity=0.0,
                )
            )
        else:
            comparisons.append(
                StepComparison(
                    step_index=i,
                    status="added",
                    baseline_action=None,
                    candidate_action=candidate_steps[i].action,
                    similarity=0.0,
                )
            )

    first_divergence: int | None = None
    for sc in comparisons:
        if sc.status != "match":
            first_divergence = sc.step_index
            break

    total_sim = sum(sc.similarity for sc in comparisons)
    similarity_score = total_sim / len(comparisons)

    if similarity_score >= 0.95:
        verdict = "identical"
    elif similarity_score >= 0.6:
        verdict = "minor_drift"
    else:
        verdict = "major_divergence"

    return TraceComparison(
        baseline_id=baseline.trace_id,
        candidate_id=candidate.trace_id,
        step_comparisons=comparisons,
        first_divergence=first_divergence,
        similarity_score=similarity_score,
        verdict=verdict,
    )
