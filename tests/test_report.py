"""Tests for notarize.report formatters."""

from __future__ import annotations

import io
import json

from rich.console import Console

from notarize.report import print_result, print_trace, to_json, to_markdown
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import VerificationResult


def _console(buf: io.StringIO) -> Console:
    return Console(file=buf, highlight=False, no_color=True)


def _make_result(verdict: str = "verified") -> VerificationResult:
    return VerificationResult(
        trace_id="trace-001",
        verdict=verdict,
        checks_passed=["hash_chain_integrity", "merkle_root_valid"],
        checks_failed=[],
        error=None,
        timestamp=100.0,
    )


def _make_trace() -> AgentTrace:
    steps = [
        TraceStep(0, "tool_call:search", "found results", "success", tool_name="search"),
        TraceStep(1, "tool_call:write", "wrote output", "success", tool_name="write"),
    ]
    return AgentTrace("trace-001", "test-agent", "Search and process", steps, created_at=0.0)


# ── print_result ──────────────────────────────────────────────────────────────


def test_print_result_verified() -> None:
    buf = io.StringIO()
    result = _make_result("verified")
    print_result(result, console=_console(buf))
    output = buf.getvalue()
    assert "VERIFIED" in output or "verified" in output.lower()


def test_print_result_tampered() -> None:
    buf = io.StringIO()
    result = VerificationResult("tid", "tampered", [], ["hash_chain_integrity"], None, 100.0)
    print_result(result, console=_console(buf))
    output = buf.getvalue()
    assert "TAMPERED" in output or "tampered" in output.lower()


def test_print_result_with_error() -> None:
    buf = io.StringIO()
    result = VerificationResult(
        "tid", "invalid", [], ["unexpected_error"], "Something broke", 100.0
    )
    print_result(result, console=_console(buf))
    output = buf.getvalue()
    assert "Something broke" in output or "Error" in output


def test_print_result_shows_checks_passed() -> None:
    buf = io.StringIO()
    result = _make_result("verified")
    print_result(result, console=_console(buf))
    output = buf.getvalue()
    assert "hash_chain_integrity" in output


def test_print_result_consistent() -> None:
    buf = io.StringIO()
    result = VerificationResult(
        "tid", "consistent", ["merkle_root_valid"], ["trace_id_valid"], None, 0.0
    )
    print_result(result, console=_console(buf))
    assert buf.getvalue()


# ── print_trace ───────────────────────────────────────────────────────────────


def test_print_trace_shows_trace_id() -> None:
    buf = io.StringIO()
    trace = _make_trace()
    print_trace(trace, console=_console(buf))
    output = buf.getvalue()
    assert "trace-001" in output


def test_print_trace_shows_steps() -> None:
    buf = io.StringIO()
    trace = _make_trace()
    print_trace(trace, console=_console(buf))
    output = buf.getvalue()
    assert "tool_call:search" in output or "search" in output


def test_print_trace_empty_steps() -> None:
    buf = io.StringIO()
    trace = AgentTrace("t", "agent", "task", [], created_at=0.0)
    print_trace(trace, console=_console(buf))
    assert "No steps" in buf.getvalue()


# ── to_json ───────────────────────────────────────────────────────────────────


def test_to_json_with_trace() -> None:
    trace = _make_trace()
    result = json.loads(to_json(trace=trace))
    assert "trace" in result
    assert result["trace"]["trace_id"] == "trace-001"


def test_to_json_with_result() -> None:
    result_obj = _make_result()
    output = json.loads(to_json(result=result_obj))
    assert "result" in output
    assert output["verdict"] == "verified"


def test_to_json_with_both() -> None:
    trace = _make_trace()
    result_obj = _make_result()
    output = json.loads(to_json(trace=trace, result=result_obj))
    assert "trace" in output
    assert "result" in output


def test_to_json_empty() -> None:
    output = json.loads(to_json())
    assert isinstance(output, dict)


# ── to_markdown ───────────────────────────────────────────────────────────────


def test_to_markdown_empty() -> None:
    md = to_markdown([])
    assert "notarize" in md
    assert "No verification results" in md


def test_to_markdown_with_results() -> None:
    results = [_make_result("verified"), _make_result("tampered")]
    md = to_markdown(results)
    assert "notarize" in md
    assert "|" in md  # has table
    assert "verified" in md
    assert "tampered" in md


def test_to_markdown_shows_trace_id() -> None:
    results = [_make_result("verified")]
    md = to_markdown(results)
    assert "trace-001" in md


def test_to_markdown_truncates_long_list() -> None:
    results = [VerificationResult(f"t{i}", "verified", [], [], None, float(i)) for i in range(25)]
    md = to_markdown(results)
    assert "more" in md
