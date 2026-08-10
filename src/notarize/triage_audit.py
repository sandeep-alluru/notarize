"""TRIAGE-SPLIT — multi-agent triage audit under capacity (arXiv 2608.06949).

Public case: *Does Splitting a Triage Decision Across Agents Hide Bias or
Help Catch It?* Single-model resource allocation shows demographic bias;
deployments use role-split pipelines (assessment → allocation → independent
audit) under audit capacity constraints. Bias can persist when:

  * allocation claims are shipped **without** an independent audit stage
  * the same agent plays assessment+allocation+audit (no role separation)
  * paired clinically identical cases diverge only on demographic attributes
    and the pipeline still claims “audited fair”

Product role in notarize (SILENT-SUCCESS / TRACE-COMPILE twin):
  Gate multi-agent decision pipelines so claimed audit success is not silent
  when the audit stage is missing, non-independent, or bias pairs disagree.

Non-Ornament:
  Call ``gate_triage_audit`` before accepting multi-agent resource-allocation
  outcomes as audited. Pair with ``gate_claimed_success`` on the trace.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from notarize.closed_loop import ClosedLoopError, GateOutcome

PIPELINE_ROLES: frozenset[str] = frozenset(
    {
        "assessment",
        "assess",
        "triage",
        "allocation",
        "allocate",
        "assign",
        "audit",
        "review",
        "independent_audit",
    }
)

ASSESSMENT_ROLES: frozenset[str] = frozenset({"assessment", "assess", "triage"})
ALLOCATION_ROLES: frozenset[str] = frozenset({"allocation", "allocate", "assign"})
AUDIT_ROLES: frozenset[str] = frozenset({"audit", "review", "independent_audit"})


@dataclass(frozen=True)
class TriageStage:
    """One role-differentiated step in a multi-agent triage pipeline."""

    stage_id: str
    role: str
    agent_id: str
    case_id: str
    decision: str = ""  # allocate | defer | deny | escalate | ...
    demographic_key: str = ""
    demographic_value: str = ""
    independent: bool = True  # audit independence claim
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "role": self.role,
            "agent_id": self.agent_id,
            "case_id": self.case_id,
            "decision": self.decision,
            "demographic_key": self.demographic_key,
            "demographic_value": self.demographic_value,
            "independent": self.independent,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class PairedTriageCase:
    """Two clinically matched cases differing by one demographic attribute."""

    pair_id: str
    case_id_a: str
    case_id_b: str
    decision_a: str
    decision_b: str
    demographic_key: str
    clinically_identical: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "case_id_a": self.case_id_a,
            "case_id_b": self.case_id_b,
            "decision_a": self.decision_a,
            "decision_b": self.decision_b,
            "demographic_key": self.demographic_key,
            "clinically_identical": self.clinically_identical,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class TriageAuditReport:
    """Analysis of multi-agent triage pipeline integrity."""

    stage_count: int
    case_ids: tuple[str, ...]
    roles_present: tuple[str, ...]
    missing_roles: tuple[str, ...]
    non_independent_audits: tuple[str, ...]
    same_agent_role_collapse: tuple[str, ...]
    biased_pairs: tuple[str, ...]
    unaudited_allocations: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_count": self.stage_count,
            "case_ids": list(self.case_ids),
            "roles_present": list(self.roles_present),
            "missing_roles": list(self.missing_roles),
            "non_independent_audits": list(self.non_independent_audits),
            "same_agent_role_collapse": list(self.same_agent_role_collapse),
            "biased_pairs": list(self.biased_pairs),
            "unaudited_allocations": list(self.unaudited_allocations),
            "details": dict(self.details),
        }


def _canon(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _role_bucket(role: str) -> str:
    r = _canon(role)
    if r in ASSESSMENT_ROLES:
        return "assessment"
    if r in ALLOCATION_ROLES:
        return "allocation"
    if r in AUDIT_ROLES:
        return "audit"
    return r


def _as_stage(item: Any, index: int = 0) -> TriageStage:
    if isinstance(item, TriageStage):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"stage must be TriageStage or dict, got {type(item)!r}")
    sid = str(item.get("stage_id") or item.get("id") or f"stage_{index}").strip()
    role = str(item.get("role") or item.get("stage") or "").strip()
    agent = str(item.get("agent_id") or item.get("agent") or "").strip()
    case = str(item.get("case_id") or item.get("case") or "").strip()
    if not role:
        raise ValueError(f"stage {sid!r} missing role")
    if not agent:
        raise ValueError(f"stage {sid!r} missing agent_id")
    if not case:
        raise ValueError(f"stage {sid!r} missing case_id")
    return TriageStage(
        stage_id=sid,
        role=role,
        agent_id=agent,
        case_id=case,
        decision=str(item.get("decision") or item.get("outcome") or ""),
        demographic_key=str(item.get("demographic_key") or item.get("demo_key") or ""),
        demographic_value=str(item.get("demographic_value") or item.get("demo_value") or ""),
        independent=bool(item.get("independent", True)),
        meta=dict(item.get("meta") or {}) if isinstance(item.get("meta"), dict) else {},
    )


def _as_pair(item: Any, index: int = 0) -> PairedTriageCase:
    if isinstance(item, PairedTriageCase):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"pair must be PairedTriageCase or dict, got {type(item)!r}")
    pid = str(item.get("pair_id") or item.get("id") or f"pair_{index}").strip()
    return PairedTriageCase(
        pair_id=pid,
        case_id_a=str(item.get("case_id_a") or item.get("a") or "").strip(),
        case_id_b=str(item.get("case_id_b") or item.get("b") or "").strip(),
        decision_a=_canon(str(item.get("decision_a") or item.get("outcome_a") or "")),
        decision_b=_canon(str(item.get("decision_b") or item.get("outcome_b") or "")),
        demographic_key=str(item.get("demographic_key") or item.get("demo_key") or ""),
        clinically_identical=bool(item.get("clinically_identical", True)),
        meta=dict(item.get("meta") or {}) if isinstance(item.get("meta"), dict) else {},
    )


def analyze_triage_pipeline(
    stages: Sequence[Any] | None,
    pairs: Sequence[Any] | None = None,
    *,
    required_roles: Sequence[str] | None = None,
) -> TriageAuditReport:
    """Analyze multi-agent triage stages and optional demographic pairs."""
    parsed = [_as_stage(s, i) for i, s in enumerate(stages or [])]
    req = [_role_bucket(r) for r in (required_roles or ["assessment", "allocation", "audit"])]
    roles = tuple(dict.fromkeys(_role_bucket(s.role) for s in parsed))
    present = set(roles)
    missing = tuple(r for r in req if r not in present)

    # Per-case allocation vs audit
    by_case: dict[str, list[TriageStage]] = {}
    for s in parsed:
        by_case.setdefault(s.case_id, []).append(s)

    unaudited: list[str] = []
    non_indep: list[str] = []
    collapse: list[str] = []

    for case_id, st_list in by_case.items():
        buckets: dict[str, list[TriageStage]] = {}
        for s in st_list:
            buckets.setdefault(_role_bucket(s.role), []).append(s)
        has_alloc = bool(buckets.get("allocation"))
        has_audit = bool(buckets.get("audit"))
        if has_alloc and not has_audit:
            unaudited.append(case_id)
        for a in buckets.get("audit") or []:
            if not a.independent:
                non_indep.append(a.stage_id)
            # independence: audit agent must differ from allocation agent
            for al in buckets.get("allocation") or []:
                if _canon(a.agent_id) == _canon(al.agent_id):
                    collapse.append(f"{case_id}:{a.agent_id}")
            for asmt in buckets.get("assessment") or []:
                if (
                    _canon(a.agent_id) == _canon(asmt.agent_id)
                    and f"{case_id}:{a.agent_id}" not in collapse
                ):
                    # same agent assessment+audit also collapses independence
                    collapse.append(f"{case_id}:{a.agent_id}")

        # single agent plays all roles on case
        agents = {_canon(s.agent_id) for s in st_list}
        role_set = {_role_bucket(s.role) for s in st_list}
        if len(agents) == 1 and len(role_set) >= 2:
            only = next(iter(agents))
            key = f"{case_id}:{only}"
            if key not in collapse:
                collapse.append(key)

    biased: list[str] = []
    for i, raw in enumerate(pairs or []):
        p = _as_pair(raw, i)
        if not p.clinically_identical:
            continue
        if p.decision_a and p.decision_b and p.decision_a != p.decision_b:
            biased.append(p.pair_id)

    return TriageAuditReport(
        stage_count=len(parsed),
        case_ids=tuple(sorted(by_case.keys())),
        roles_present=roles,
        missing_roles=missing,
        non_independent_audits=tuple(dict.fromkeys(non_indep)),
        same_agent_role_collapse=tuple(dict.fromkeys(collapse)),
        biased_pairs=tuple(biased),
        unaudited_allocations=tuple(dict.fromkeys(unaudited)),
        details={"required_roles": list(req)},
    )


def gate_triage_audit(
    stages: Sequence[Any] | None,
    pairs: Sequence[Any] | None = None,
    *,
    claim_audited: bool = False,
    require_stages: bool = True,
    require_full_pipeline: bool = True,
    refuse_unaudited_allocation: bool = True,
    refuse_role_collapse: bool = True,
    refuse_non_independent_audit: bool = True,
    refuse_paired_bias: bool = True,
    required_roles: Sequence[str] | None = None,
) -> GateOutcome:
    """Refuse multi-agent triage outcomes that hide bias or skip audit.

    Public case: arXiv 2608.06949 — splitting triage across agents does not
    automatically catch demographic bias; audit capacity and independence
    matter. Claimed “pipeline audited” without an independent audit stage,
    with same-agent role collapse, or with disagreeing clinical twins is
    silent success of the fairness claim.

    Rules:

    1. ``claim_audited`` with zero stages → **FAIL_LOUD**
    2. Empty inventory when required → **FAIL_LOUD**
    3. Missing required roles (assessment/allocation/audit) when claiming
       audited full pipeline → **FAIL**
    4. Allocation without audit stage → **FAIL**
    5. Audit not independent / same agent as allocation → **FAIL**
    6. Clinically identical demographic pairs with different decisions → **FAIL**
    7. Full independent pipeline + consistent pairs → **PASS**
    """
    if not stages:
        if claim_audited or require_stages:
            return GateOutcome(
                ok=False,
                verdict="FAIL_LOUD",
                reason=(
                    "TRIAGE-SPLIT: empty stage inventory — cannot claim multi-agent "
                    f"audited triage without pipeline log (claim_audited={claim_audited}; "
                    "arXiv 2608.06949)"
                ),
                exit_code=2,
                silent_success=bool(claim_audited),
            )
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason="TRIAGE-SPLIT: no stages required",
            exit_code=0,
        )

    try:
        report = analyze_triage_pipeline(
            stages,
            pairs,
            required_roles=required_roles,
        )
    except (TypeError, ValueError) as exc:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=f"TRIAGE-SPLIT: invalid pipeline payload: {exc}",
            exit_code=2,
        )

    n = report.stage_count

    if claim_audited and require_full_pipeline and report.missing_roles:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TRIAGE-SPLIT: claim_audited but missing roles "
                f"{list(report.missing_roles)} (present={list(report.roles_present)}) "
                f"— refuse incomplete multi-agent audit pipeline (arXiv 2608.06949)"
            ),
            exit_code=1,
            silent_success=True,
            failed_step_indices=tuple(range(min(len(report.missing_roles), 8))),
            trace_id=f"stages={n}",
        )

    if refuse_unaudited_allocation and report.unaudited_allocations:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TRIAGE-SPLIT: {len(report.unaudited_allocations)} case(s) have "
                f"allocation without independent audit stage "
                f"{list(report.unaudited_allocations)[:8]} — refuse unaudited "
                f"resource allocation under audit-capacity class"
            ),
            exit_code=1,
            silent_success=True,
            degraded_step_indices=tuple(range(min(len(report.unaudited_allocations), 8))),
            trace_id=f"stages={n}",
        )

    if refuse_non_independent_audit and report.non_independent_audits:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TRIAGE-SPLIT: audit stages marked non-independent "
                f"{list(report.non_independent_audits)[:8]} — refuse captive audit"
            ),
            exit_code=1,
            silent_success=True,
            trace_id=f"stages={n}",
        )

    if refuse_role_collapse and report.same_agent_role_collapse:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TRIAGE-SPLIT: role collapse — same agent spans allocation/audit "
                f"or multi-role single-agent pipeline "
                f"{list(report.same_agent_role_collapse)[:8]} — splitting without "
                f"independence hides bias (arXiv 2608.06949)"
            ),
            exit_code=1,
            silent_success=True,
            trace_id=f"stages={n}",
        )

    if refuse_paired_bias and report.biased_pairs:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TRIAGE-SPLIT: {len(report.biased_pairs)} clinically identical "
                f"paired case(s) diverge on decision "
                f"{list(report.biased_pairs)[:8]} — demographic split without "
                f"catch; refuse claimed fair audit"
            ),
            exit_code=1,
            silent_success=True,
            failed_step_indices=tuple(range(min(len(report.biased_pairs), 8))),
            trace_id=f"stages={n}",
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"TRIAGE-SPLIT ok: stages={n} cases={len(report.case_ids)} "
            f"roles={list(report.roles_present)} biased_pairs=0 "
            f"claim_audited={claim_audited}"
        ),
        exit_code=0,
        silent_success=False,
        trace_id=f"stages={n}",
    )


def assert_triage_audit_ok(
    stages: Sequence[Any] | None,
    pairs: Sequence[Any] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_triage_audit` is ok."""
    outcome = gate_triage_audit(stages, pairs, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
