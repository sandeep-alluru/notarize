"""TraceCompiler-class workflow mining (arXiv 2608.02680).

Public case: TraceCompiler mines noisy agent traces into mostly deterministic
workflows. Hard producer→consumer edges are admitted only when a consumer
argument contains a value attributable uniquely to an earlier producer; every
hard edge carries an auditable evidence tuple. Ambiguous relations are
*suspected* and impose no ordering constraint.

Bindings: constants | user_inputs | copied_outputs | transforms | residual LLM.

Product role in notarize (attestation twin of SILENT-SUCCESS):
  Refuse "compiled" workflows that claim hard ordering without evidence, or
  that are pure residual-LLM graphs when deterministic structure is required.

Non-Ornament:
  Call ``gate_compiled_workflow`` before promoting a mined skill/workflow to
  production replay. Pair with ``gate_claimed_success`` for step honesty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

from notarize.closed_loop import ClosedLoopError, GateOutcome

BindingKind = Literal[
    "constant",
    "user_input",
    "copied_output",
    "transform",
    "llm_residual",
]

EdgeStrength = Literal["hard", "suspected"]


@dataclass(frozen=True)
class ToolInvocation:
    """One tool step in a noisy agent trace (pre-compile)."""

    step_id: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    is_retry: bool = False
    is_exploration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "outputs": dict(self.outputs),
            "is_retry": self.is_retry,
            "is_exploration": self.is_exploration,
        }


@dataclass(frozen=True)
class WorkflowEdge:
    """Producer→consumer dependency with optional evidence (TraceCompiler)."""

    producer_step: str
    consumer_step: str
    producer_key: str
    consumer_arg: str
    binding: BindingKind
    strength: EdgeStrength
    evidence: tuple[str, ...] = ()
    value_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_step": self.producer_step,
            "consumer_step": self.consumer_step,
            "producer_key": self.producer_key,
            "consumer_arg": self.consumer_arg,
            "binding": self.binding,
            "strength": self.strength,
            "evidence": list(self.evidence),
            "value_fingerprint": self.value_fingerprint,
        }


@dataclass(frozen=True)
class CompiledWorkflow:
    """Mostly deterministic workflow compiled from noisy traces."""

    step_ids: tuple[str, ...]
    edges: tuple[WorkflowEdge, ...]
    hard_edge_count: int
    suspected_edge_count: int
    residual_llm_count: int
    retry_noise_count: int
    exploration_noise_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_ids": list(self.step_ids),
            "edges": [e.to_dict() for e in self.edges],
            "hard_edge_count": self.hard_edge_count,
            "suspected_edge_count": self.suspected_edge_count,
            "residual_llm_count": self.residual_llm_count,
            "retry_noise_count": self.retry_noise_count,
            "exploration_noise_count": self.exploration_noise_count,
        }


def _fp(value: Any) -> str:
    """Stable string fingerprint for unique attribution."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        s = str(value).strip()
        return s if s else ""
    if isinstance(value, (list, tuple)):
        return "|".join(_fp(v) for v in value)
    if isinstance(value, dict):
        parts = [f"{k}={_fp(value[k])}" for k in sorted(value)]
        return "{" + ",".join(parts) + "}"
    return str(value)


def _as_invocation(item: ToolInvocation | dict[str, Any]) -> ToolInvocation:
    if isinstance(item, ToolInvocation):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"invocation must be ToolInvocation or dict, got {type(item)!r}")
    sid = str(item.get("step_id") or item.get("id") or "").strip()
    if not sid:
        raise ValueError("invocation missing step_id")
    tool = str(item.get("tool") or item.get("name") or "tool").strip() or "tool"
    args = item.get("arguments") or item.get("args") or {}
    outs = item.get("outputs") or item.get("output") or item.get("result") or {}
    if not isinstance(args, dict):
        args = {"_raw": args}
    if not isinstance(outs, dict):
        outs = {"_value": outs}
    return ToolInvocation(
        step_id=sid,
        tool=tool,
        arguments=dict(args),
        outputs=dict(outs),
        is_retry=bool(item.get("is_retry") or item.get("retry")),
        is_exploration=bool(item.get("is_exploration") or item.get("exploration")),
    )


def _as_edge(item: WorkflowEdge | dict[str, Any]) -> WorkflowEdge:
    if isinstance(item, WorkflowEdge):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"edge must be WorkflowEdge or dict, got {type(item)!r}")
    binding = str(item.get("binding") or "llm_residual").strip().lower()
    if binding not in {
        "constant",
        "user_input",
        "copied_output",
        "transform",
        "llm_residual",
    }:
        binding = "llm_residual"
    strength = str(item.get("strength") or "suspected").strip().lower()
    if strength not in {"hard", "suspected"}:
        strength = "suspected"
    ev = item.get("evidence") or ()
    if isinstance(ev, str):
        evidence: tuple[str, ...] = (ev,) if ev else ()
    else:
        evidence = tuple(str(x) for x in ev)
    return WorkflowEdge(
        producer_step=str(item.get("producer_step") or item.get("producer") or ""),
        consumer_step=str(item.get("consumer_step") or item.get("consumer") or ""),
        producer_key=str(item.get("producer_key") or item.get("out_key") or ""),
        consumer_arg=str(item.get("consumer_arg") or item.get("arg") or ""),
        binding=binding,  # type: ignore[arg-type]
        strength=strength,  # type: ignore[arg-type]
        evidence=evidence,
        value_fingerprint=str(item.get("value_fingerprint") or item.get("fp") or ""),
    )


def compile_trace_workflow(
    invocations: Sequence[ToolInvocation | dict[str, Any]],
    *,
    drop_retries: bool = True,
    drop_exploration: bool = True,
) -> CompiledWorkflow:
    """Mine producer→consumer edges from tool invocations (deterministic).

    Hard edge rule (TraceCompiler):
      Admit a **hard** edge only when a consumer argument value is uniquely
      attributable to exactly one earlier producer's output value. Evidence
      tuple = (producer_step, producer_key, consumer_arg, fingerprint).

    Ambiguous (value appears in 0 or ≥2 producers) → **suspected** edge with
    empty/weak evidence and **no hard ordering** obligation.

    Argument values that match no producer:
      * empty / None → constant (if literal-looking) or user_input
      * otherwise → llm_residual suspected edge from previous step (weak)
    """
    invs = [_as_invocation(x) for x in invocations]
    retry_n = sum(1 for i in invs if i.is_retry)
    explor_n = sum(1 for i in invs if i.is_exploration)

    kept: list[ToolInvocation] = []
    for inv in invs:
        if drop_retries and inv.is_retry:
            continue
        if drop_exploration and inv.is_exploration:
            continue
        kept.append(inv)

    # Map fingerprint → list of (step_id, out_key) producers
    producers_by_fp: dict[str, list[tuple[str, str]]] = {}
    for inv in kept:
        for key, val in inv.outputs.items():
            fp = _fp(val)
            if not fp:
                continue
            producers_by_fp.setdefault(fp, []).append((inv.step_id, key))

    edges: list[WorkflowEdge] = []
    residual = 0
    step_ids = tuple(i.step_id for i in kept)

    for inv in kept:
        for arg_name, arg_val in inv.arguments.items():
            fp = _fp(arg_val)
            if not fp:
                # empty arg — treat as user_input residual (no hard edge)
                residual += 1
                edges.append(
                    WorkflowEdge(
                        producer_step="",
                        consumer_step=inv.step_id,
                        producer_key="",
                        consumer_arg=arg_name,
                        binding="user_input",
                        strength="suspected",
                        evidence=(),
                        value_fingerprint="",
                    )
                )
                continue

            matches = producers_by_fp.get(fp, [])
            # only earlier producers
            earlier = [
                (sid, key)
                for sid, key in matches
                if sid != inv.step_id and step_ids.index(sid) < step_ids.index(inv.step_id)
            ]

            if len(earlier) == 1:
                prod_step, prod_key = earlier[0]
                evidence = (
                    f"producer={prod_step}",
                    f"out={prod_key}",
                    f"arg={arg_name}",
                    f"fp={fp[:64]}",
                )
                edges.append(
                    WorkflowEdge(
                        producer_step=prod_step,
                        consumer_step=inv.step_id,
                        producer_key=prod_key,
                        consumer_arg=arg_name,
                        binding="copied_output",
                        strength="hard",
                        evidence=evidence,
                        value_fingerprint=fp[:128],
                    )
                )
            elif len(earlier) > 1:
                # ambiguous — suspected, no hard ordering
                prod_step, prod_key = earlier[0]
                edges.append(
                    WorkflowEdge(
                        producer_step=prod_step,
                        consumer_step=inv.step_id,
                        producer_key=prod_key,
                        consumer_arg=arg_name,
                        binding="copied_output",
                        strength="suspected",
                        evidence=(f"ambiguous_producers={len(earlier)}",),
                        value_fingerprint=fp[:128],
                    )
                )
            else:
                # no producer — constant if short literal-like, else llm residual
                is_const = (
                    isinstance(arg_val, (int, float, bool))
                    or (isinstance(arg_val, str) and len(arg_val) < 40 and " " not in arg_val.strip())
                )
                if is_const:
                    edges.append(
                        WorkflowEdge(
                            producer_step="",
                            consumer_step=inv.step_id,
                            producer_key="",
                            consumer_arg=arg_name,
                            binding="constant",
                            strength="suspected",
                            evidence=(f"literal={fp[:40]}",),
                            value_fingerprint=fp[:128],
                        )
                    )
                else:
                    residual += 1
                    prev = ""
                    idx = step_ids.index(inv.step_id)
                    if idx > 0:
                        prev = step_ids[idx - 1]
                    edges.append(
                        WorkflowEdge(
                            producer_step=prev,
                            consumer_step=inv.step_id,
                            producer_key="",
                            consumer_arg=arg_name,
                            binding="llm_residual",
                            strength="suspected",
                            evidence=(),
                            value_fingerprint=fp[:128],
                        )
                    )

    hard_n = sum(1 for e in edges if e.strength == "hard")
    sus_n = sum(1 for e in edges if e.strength == "suspected")
    return CompiledWorkflow(
        step_ids=step_ids,
        edges=tuple(edges),
        hard_edge_count=hard_n,
        suspected_edge_count=sus_n,
        residual_llm_count=residual,
        retry_noise_count=retry_n,
        exploration_noise_count=explor_n,
    )


def hard_edges_missing_evidence(edges: Sequence[WorkflowEdge]) -> list[WorkflowEdge]:
    """Hard edges must carry non-empty evidence tuples."""
    bad: list[WorkflowEdge] = []
    for e in edges:
        if e.strength != "hard":
            continue
        if not e.evidence or not e.producer_step or not e.consumer_step:
            bad.append(e)
        elif not e.value_fingerprint and e.binding == "copied_output":
            bad.append(e)
    return bad


def gate_compiled_workflow(
    workflow: CompiledWorkflow | Sequence[WorkflowEdge] | None = None,
    *,
    invocations: Sequence[ToolInvocation | dict[str, Any]] | None = None,
    require_workflow: bool = True,
    require_hard_edges: bool = False,
    min_hard_edges: int = 0,
    refuse_hard_without_evidence: bool = True,
    refuse_all_llm_residual: bool = True,
    max_residual_ratio: float = 1.0,
) -> GateOutcome:
    """Refuse unattested or purely residual compiled workflows (TRACE-COMPILE).

    Rules:

    * No workflow when required → **FAIL_LOUD**
    * Hard edge without evidence → **FAIL_LOUD** (audit break)
    * ``require_hard_edges`` and hard_edge_count < min → **FAIL**
    * All bindings residual LLM when refuse_all_llm_residual and edges exist → **FAIL**
    * residual ratio > max_residual_ratio → **FAIL**
    * Suspected edges alone do **not** fail ordering (TraceCompiler)
    * Clean hard edges with evidence → **PASS**
    """
    wf: CompiledWorkflow | None = None
    edges: list[WorkflowEdge] = []

    if invocations is not None and workflow is None:
        wf = compile_trace_workflow(invocations)
        edges = list(wf.edges)
    elif isinstance(workflow, CompiledWorkflow):
        wf = workflow
        edges = list(workflow.edges)
    elif workflow is not None:
        try:
            edges = [_as_edge(e) for e in workflow]
        except (TypeError, ValueError) as exc:
            return GateOutcome(
                ok=False,
                verdict="FAIL_LOUD",
                reason=f"TRACE-COMPILE: invalid edge payload: {exc}",
                exit_code=2,
            )
        hard_n = sum(1 for e in edges if e.strength == "hard")
        sus_n = len(edges) - hard_n
        residual = sum(1 for e in edges if e.binding == "llm_residual")
        wf = CompiledWorkflow(
            step_ids=tuple(
                dict.fromkeys(
                    [e.producer_step for e in edges if e.producer_step]
                    + [e.consumer_step for e in edges if e.consumer_step]
                )
            ),
            edges=tuple(edges),
            hard_edge_count=hard_n,
            suspected_edge_count=sus_n,
            residual_llm_count=residual,
            retry_noise_count=0,
            exploration_noise_count=0,
        )
    else:
        edges = []
        wf = None

    if require_workflow and (wf is None or (not edges and not (wf and wf.step_ids))):
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=(
                "TRACE-COMPILE: no compiled workflow — cannot promote empty "
                "trace mining as a skill/workflow (arXiv 2608.02680)"
            ),
            exit_code=2,
        )

    if wf is None:
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason="TRACE-COMPILE: no workflow required; nothing to gate",
            exit_code=0,
        )

    if refuse_hard_without_evidence:
        bad = hard_edges_missing_evidence(wf.edges)
        if bad:
            return GateOutcome(
                ok=False,
                verdict="FAIL_LOUD",
                reason=(
                    f"TRACE-COMPILE: {len(bad)} hard edge(s) lack auditable evidence "
                    f"(producer/consumer/fingerprint) — refuse unattested ordering "
                    f"ids={[f'{b.producer_step}->{b.consumer_step}' for b in bad[:6]]}"
                ),
                exit_code=2,
            )

    if require_hard_edges and wf.hard_edge_count < max(min_hard_edges, 1):
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TRACE-COMPILE: hard_edge_count={wf.hard_edge_count} < "
                f"required={max(min_hard_edges, 1)} — workflow has no unique "
                "producer→consumer attributions (mostly noise/retries)"
            ),
            exit_code=1,
        )

    if min_hard_edges > 0 and wf.hard_edge_count < min_hard_edges:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TRACE-COMPILE: hard_edge_count={wf.hard_edge_count} < "
                f"min_hard_edges={min_hard_edges}"
            ),
            exit_code=1,
        )

    edge_n = len(wf.edges)
    if edge_n > 0 and refuse_all_llm_residual:
        residual = sum(1 for e in wf.edges if e.binding == "llm_residual")
        if residual == edge_n:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    "TRACE-COMPILE: all edges are llm_residual — compiled workflow "
                    "is not mostly-deterministic; refuse promotion to replay skill "
                    "(TraceCompiler residual class)"
                ),
                exit_code=1,
            )
        ratio = residual / edge_n
        if ratio > max_residual_ratio:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(
                    f"TRACE-COMPILE: residual_llm ratio={ratio:.2f} > "
                    f"max={max_residual_ratio:.2f} (residual={residual}/{edge_n})"
                ),
                exit_code=1,
            )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"TRACE-COMPILE ok: steps={len(wf.step_ids)} hard={wf.hard_edge_count} "
            f"suspected={wf.suspected_edge_count} residual={wf.residual_llm_count} "
            f"retries_dropped={wf.retry_noise_count}"
        ),
        exit_code=0,
    )


def assert_compiled_workflow_ok(
    workflow: CompiledWorkflow | Sequence[WorkflowEdge] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_compiled_workflow` is ok."""
    outcome = gate_compiled_workflow(workflow, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
