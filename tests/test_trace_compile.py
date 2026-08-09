"""TRACE-COMPILE - TraceCompiler workflow mining (arXiv 2608.02680).

Hard edges require unique producer→consumer attribution + evidence.
Suspected edges impose no ordering. Pure residual-LLM workflows fail gate.
"""

from __future__ import annotations

import pytest

from notarize.closed_loop import ClosedLoopError
from notarize.trace_compile import (
    ToolInvocation,
    WorkflowEdge,
    assert_compiled_workflow_ok,
    compile_trace_workflow,
    gate_compiled_workflow,
    hard_edges_missing_evidence,
)


def test_compile_hard_edge_unique_copy() -> None:
    invs = [
        ToolInvocation("s1", "search", arguments={"q": "x"}, outputs={"hit_id": "H99"}),
        ToolInvocation(
            "s2",
            "fetch",
            arguments={"id": "H99"},
            outputs={"body": "..."},
        ),
    ]
    wf = compile_trace_workflow(invs)
    assert wf.hard_edge_count == 1
    hard = [e for e in wf.edges if e.strength == "hard"]
    assert hard[0].producer_step == "s1"
    assert hard[0].consumer_step == "s2"
    assert hard[0].binding == "copied_output"
    assert hard[0].evidence
    assert hard[0].value_fingerprint == "H99"


def test_ambiguous_producers_are_suspected() -> None:
    invs = [
        ToolInvocation("a", "t1", outputs={"v": "SAME"}),
        ToolInvocation("b", "t2", outputs={"v": "SAME"}),
        ToolInvocation("c", "t3", arguments={"x": "SAME"}, outputs={}),
    ]
    wf = compile_trace_workflow(invs)
    # two earlier producers for SAME → suspected, not hard
    assert wf.hard_edge_count == 0
    assert any(e.strength == "suspected" for e in wf.edges)


def test_retries_dropped() -> None:
    invs = [
        ToolInvocation("s1", "search", outputs={"id": "1"}, is_retry=False),
        ToolInvocation("s1r", "search", outputs={"id": "1"}, is_retry=True),
        ToolInvocation("s2", "use", arguments={"id": "1"}),
    ]
    wf = compile_trace_workflow(invs, drop_retries=True)
    assert "s1r" not in wf.step_ids
    assert wf.retry_noise_count == 1
    assert wf.hard_edge_count == 1


def test_gate_empty_fails_loud() -> None:
    out = gate_compiled_workflow(require_workflow=True)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert "TRACE-COMPILE" in out.reason


def test_gate_hard_without_evidence_fails_loud() -> None:
    bad = WorkflowEdge(
        producer_step="p",
        consumer_step="c",
        producer_key="k",
        consumer_arg="a",
        binding="copied_output",
        strength="hard",
        evidence=(),  # missing
        value_fingerprint="x",
    )
    out = gate_compiled_workflow([bad])
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert "evidence" in out.reason.lower()


def test_gate_all_llm_residual_fails() -> None:
    edges = [
        WorkflowEdge(
            producer_step="a",
            consumer_step="b",
            producer_key="",
            consumer_arg="prompt",
            binding="llm_residual",
            strength="suspected",
            evidence=(),
        ),
        WorkflowEdge(
            producer_step="b",
            consumer_step="c",
            producer_key="",
            consumer_arg="thought",
            binding="llm_residual",
            strength="suspected",
            evidence=(),
        ),
    ]
    out = gate_compiled_workflow(edges, refuse_all_llm_residual=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "llm_residual" in out.reason


def test_gate_from_invocations_passes() -> None:
    invs = [
        {"step_id": "1", "tool": "list", "outputs": {"path": "out/a"}},
        {"step_id": "2", "tool": "read", "arguments": {"path": "out/a"}, "outputs": {"n": 3}},
        {
            "step_id": "3",
            "tool": "sum",
            "arguments": {"n": 3, "mode": "fast"},
            "outputs": {"total": 3},
        },
    ]
    out = gate_compiled_workflow(invocations=invs, require_hard_edges=True)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert "hard=" in out.reason


def test_require_hard_edges_fails_on_noise() -> None:
    invs = [
        ToolInvocation("1", "think", arguments={"q": "what next?"}, outputs={}),
        ToolInvocation("2", "think", arguments={"q": "still thinking"}, outputs={}),
    ]
    out = gate_compiled_workflow(invocations=invs, require_hard_edges=True)
    assert out.ok is False
    assert out.verdict == "FAIL"


def test_suspected_only_ok_when_hard_not_required() -> None:
    invs = [
        ToolInvocation("1", "a", arguments={"k": "literal"}, outputs={}),
    ]
    out = gate_compiled_workflow(
        invocations=invs,
        require_hard_edges=False,
        refuse_all_llm_residual=False,
    )
    assert out.ok is True


def test_hard_edges_missing_evidence_helper() -> None:
    good = WorkflowEdge("p", "c", "k", "a", "copied_output", "hard", ("e1",), "v")
    bad = WorkflowEdge("p", "c", "k", "a", "copied_output", "hard", (), "v")
    assert hard_edges_missing_evidence([good]) == []
    assert len(hard_edges_missing_evidence([bad])) == 1


def test_assert_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_compiled_workflow_ok(require_workflow=True)


def test_arxiv_tracecompiler_fixture() -> None:
    """End-to-end: noisy retries → hard evidence edges → gate PASS."""
    # Noisy rediscovery of list→read→summarize with a failed retry in the middle
    invs = [
        ToolInvocation("t1", "list_dir", arguments={"root": "/proj"}, outputs={"files": "a.py"}),
        ToolInvocation(
            "t1b",
            "list_dir",
            arguments={"root": "/proj"},
            outputs={"files": "a.py"},
            is_retry=True,
        ),
        ToolInvocation(
            "t2",
            "read_file",
            arguments={"path": "a.py"},
            outputs={"text": "def main(): ..."},
        ),
        ToolInvocation(
            "t3",
            "summarize",
            arguments={"text": "def main(): ...", "style": "short"},
            outputs={"summary": "entry point"},
        ),
        ToolInvocation(
            "tx",
            "explore",
            arguments={"note": "maybe unrelated"},
            outputs={},
            is_exploration=True,
        ),
    ]
    wf = compile_trace_workflow(invs)
    assert wf.retry_noise_count == 1
    assert wf.exploration_noise_count == 1
    assert "t1b" not in wf.step_ids
    assert "tx" not in wf.step_ids
    assert wf.hard_edge_count >= 2  # files→path and text→text
    out = gate_compiled_workflow(wf, require_hard_edges=True, min_hard_edges=2)
    assert out.ok is True
    assert out.verdict == "PASS"
    d = wf.to_dict()
    assert d["hard_edge_count"] == wf.hard_edge_count


def test_max_residual_ratio() -> None:
    edges = [
        WorkflowEdge("a", "b", "k", "x", "copied_output", "hard", ("e",), "v"),
        WorkflowEdge("b", "c", "", "p", "llm_residual", "suspected", ()),
        WorkflowEdge("c", "d", "", "q", "llm_residual", "suspected", ()),
    ]
    out = gate_compiled_workflow(edges, max_residual_ratio=0.3, refuse_all_llm_residual=True)
    assert out.ok is False
    assert "ratio" in out.reason.lower() or "residual" in out.reason.lower()
