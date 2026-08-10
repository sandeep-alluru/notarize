"""TRIAGE-SPLIT — multi-agent triage audit (arXiv 2608.06949).

Public case (Track B 20260810T201238Z):
  Splitting triage across agents does not automatically catch demographic
  bias; independent audit capacity and paired-case consistency matter.
"""

from __future__ import annotations

import pytest

from notarize.closed_loop import ClosedLoopError
from notarize.triage_audit import (
    PairedTriageCase,
    TriageStage,
    analyze_triage_pipeline,
    assert_triage_audit_ok,
    gate_triage_audit,
)


def _full_pipeline(case_id: str = "c1", decision: str = "allocate") -> list[TriageStage]:
    return [
        TriageStage(
            stage_id=f"{case_id}-assess",
            role="assessment",
            agent_id="agent_assess",
            case_id=case_id,
            decision="priority_high",
        ),
        TriageStage(
            stage_id=f"{case_id}-alloc",
            role="allocation",
            agent_id="agent_alloc",
            case_id=case_id,
            decision=decision,
        ),
        TriageStage(
            stage_id=f"{case_id}-audit",
            role="audit",
            agent_id="agent_audit",
            case_id=case_id,
            decision="confirm",
            independent=True,
        ),
    ]


def test_empty_claim_audited_fails_loud() -> None:
    out = gate_triage_audit([], claim_audited=True)
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.silent_success is True
    assert "TRIAGE-SPLIT" in out.reason


def test_full_independent_pipeline_passes() -> None:
    out = gate_triage_audit(_full_pipeline(), claim_audited=True)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0


def test_missing_audit_role_fails() -> None:
    stages = [
        TriageStage(
            stage_id="a",
            role="assessment",
            agent_id="a1",
            case_id="c1",
            decision="ok",
        ),
        TriageStage(
            stage_id="b",
            role="allocation",
            agent_id="a2",
            case_id="c1",
            decision="allocate",
        ),
    ]
    out = gate_triage_audit(stages, claim_audited=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "missing" in out.reason.lower() or "audit" in out.reason.lower()


def test_unaudited_allocation_fails() -> None:
    stages = [
        {
            "stage_id": "1",
            "role": "allocation",
            "agent_id": "alloc",
            "case_id": "patient_9",
            "decision": "allocate",
        }
    ]
    out = gate_triage_audit(
        stages,
        claim_audited=False,
        require_full_pipeline=False,
        refuse_unaudited_allocation=True,
    )
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "unaudited" in out.reason.lower() or "TRIAGE-SPLIT" in out.reason


def test_role_collapse_same_agent_fails() -> None:
    stages = [
        TriageStage(
            stage_id="1",
            role="assessment",
            agent_id="solo",
            case_id="c1",
            decision="p1",
        ),
        TriageStage(
            stage_id="2",
            role="allocation",
            agent_id="solo",
            case_id="c1",
            decision="allocate",
        ),
        TriageStage(
            stage_id="3",
            role="audit",
            agent_id="solo",
            case_id="c1",
            decision="ok",
            independent=True,
        ),
    ]
    out = gate_triage_audit(stages, claim_audited=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "collapse" in out.reason.lower() or "same agent" in out.reason.lower()


def test_non_independent_audit_fails() -> None:
    stages = _full_pipeline()
    # replace audit with independent=False
    stages[-1] = TriageStage(
        stage_id="c1-audit",
        role="audit",
        agent_id="agent_audit",
        case_id="c1",
        decision="confirm",
        independent=False,
    )
    out = gate_triage_audit(stages, claim_audited=True)
    assert out.ok is False
    assert "independent" in out.reason.lower() or "TRIAGE-SPLIT" in out.reason


def test_paired_demographic_bias_fails() -> None:
    stages = _full_pipeline("cA", "allocate") + _full_pipeline("cB", "deny")
    pairs = [
        PairedTriageCase(
            pair_id="pair1",
            case_id_a="cA",
            case_id_b="cB",
            decision_a="allocate",
            decision_b="deny",
            demographic_key="age_group",
            clinically_identical=True,
        )
    ]
    out = gate_triage_audit(stages, pairs, claim_audited=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "pair" in out.reason.lower() or "demographic" in out.reason.lower()
    assert out.silent_success is True


def test_paired_consistent_decisions_pass() -> None:
    stages = _full_pipeline("cA", "allocate") + _full_pipeline("cB", "allocate")
    pairs = [
        {
            "pair_id": "p1",
            "case_id_a": "cA",
            "case_id_b": "cB",
            "decision_a": "allocate",
            "decision_b": "allocate",
            "demographic_key": "sex",
            "clinically_identical": True,
        }
    ]
    out = gate_triage_audit(stages, pairs, claim_audited=True)
    assert out.ok is True


def test_analyze_report() -> None:
    report = analyze_triage_pipeline(_full_pipeline())
    assert report.stage_count == 3
    assert "audit" in report.roles_present
    assert report.to_dict()["stage_count"] == 3


def test_assert_raises_and_passes() -> None:
    with pytest.raises(ClosedLoopError):
        assert_triage_audit_ok([], claim_audited=True)
    out = assert_triage_audit_ok(_full_pipeline(), claim_audited=True)
    assert out.ok is True


def test_invalid_payload_fails_loud() -> None:
    out = gate_triage_audit([{"stage_id": "x", "role": "audit"}])  # missing agent/case
    assert out.verdict == "FAIL_LOUD"
