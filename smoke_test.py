"""
End-to-end smoke test for tracemarket.

Simulates a user who just cloned the repo and wants to verify everything works.
No mocking, no fixtures — real behaviour, real CLI, real HTTP server.

Run from repo root:
    python smoke_test.py
    python smoke_test.py --verbose

Exit 0 = all passed. Exit 1 = at least one failure.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
REPO_ROOT = Path(__file__).parent
PYTHON = sys.executable

passed: list[str] = []
failed: list[tuple[str, str]] = []


def ok(name: str) -> None:
    passed.append(name)
    print(f"  {GREEN}✓{RESET} {name}")


def fail(name: str, reason: str) -> None:
    failed.append((name, reason))
    print(f"  {RED}✗{RESET} {name}")
    if VERBOSE:
        print(f"    {YELLOW}{reason}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def run(name: str, fn):  # noqa: ANN001
    try:
        fn()
        ok(name)
    except Exception as exc:
        reason = str(exc) if not VERBOSE else traceback.format_exc().strip()
        fail(name, reason)


# ── 1. Package import ─────────────────────────────────────────────────────────

section("1. Package import")

def _test_import_version():
    import tracemarket
    assert tracemarket.__version__, "__version__ is empty"
    assert tracemarket.__version__ != "0.0.0"

def _test_import_public_api():
    from tracemarket import (
        AgentTrace, ConsistencyVerifier, PrivacyScrubber,
        ScrubResult, TraceStep, TraceStore, VerificationResult,
    )
    assert callable(ConsistencyVerifier)
    assert callable(PrivacyScrubber)

run("tracemarket package imports", _test_import_version)
run("Public API (TraceStep, AgentTrace, ConsistencyVerifier, PrivacyScrubber, TraceStore)", _test_import_public_api)


# ── 2. Core data model ────────────────────────────────────────────────────────

section("2. Core data model (TraceStep, AgentTrace)")

def _test_tracestep_content_addressed():
    from tracemarket.trace import TraceStep
    s1 = TraceStep(0, "tool_call:search", "found 5 results", "success")
    s2 = TraceStep(0, "tool_call:search", "found 5 results", "success")
    assert s1.id == s2.id, "Same content must produce same ID"
    s3 = TraceStep(0, "tool_call:read", "found 5 results", "success")
    assert s1.id != s3.id, "Different action must produce different ID"

def _test_agenttrace_hash_chain():
    from tracemarket.trace import AgentTrace, TraceStep
    steps = [
        TraceStep(0, "action_a", "obs_a", "success"),
        TraceStep(1, "action_b", "obs_b", "success"),
        TraceStep(2, "action_c", "obs_c", "success"),
    ]
    trace = AgentTrace("t", "agent", "task", steps)
    assert steps[0].parent_id is None, "First step must have no parent"
    assert steps[1].parent_id == steps[0].id, "Step 1 parent must equal step 0 id"
    assert steps[2].parent_id == steps[1].id, "Step 2 parent must equal step 1 id"

def _test_agenttrace_merkle_root():
    from tracemarket.trace import AgentTrace, TraceStep, _sha16
    steps = [TraceStep(0, "action", "obs", "success")]
    trace = AgentTrace("t", "agent", "task", steps)
    expected = _sha16(steps[0].id)
    assert trace.merkle_root == expected, "Merkle root must match SHA-256[:16] of sorted step IDs"

def _test_agenttrace_roundtrip():
    from tracemarket.trace import AgentTrace, TraceStep
    steps = [
        TraceStep(0, "action_a", "obs_a", "success"),
        TraceStep(1, "action_b", "obs_b", "error"),
    ]
    trace = AgentTrace("t-rt", "agent", "task", steps, created_at=1234.0)
    d = trace.to_dict()
    t2 = AgentTrace.from_dict(d)
    assert t2.trace_id == trace.trace_id
    assert t2.merkle_root == trace.merkle_root
    assert len(t2.steps) == 2

run("TraceStep.id is content-addressed (same content = same ID)", _test_tracestep_content_addressed)
run("AgentTrace builds hash chain (parent_id links)", _test_agenttrace_hash_chain)
run("AgentTrace.merkle_root = SHA-256[:16] of sorted step IDs", _test_agenttrace_merkle_root)
run("AgentTrace.to_dict() / from_dict() round-trip", _test_agenttrace_roundtrip)


# ── 3. Verifier and Scrubber ──────────────────────────────────────────────────

section("3. ConsistencyVerifier + PrivacyScrubber")

def _test_verifier_valid_trace():
    from tracemarket.trace import AgentTrace, TraceStep
    from tracemarket.verifier import ConsistencyVerifier
    steps = [TraceStep(i, f"action_{i}", f"obs_{i}", "success") for i in range(3)]
    trace = AgentTrace("t", "agent", "task", steps)
    result = ConsistencyVerifier().verify(trace)
    assert result.verdict == "verified", f"Expected 'verified', got {result.verdict!r}"
    assert not result.checks_failed, f"Failed checks: {result.checks_failed}"

def _test_verifier_detects_tampered_chain():
    from tracemarket.trace import AgentTrace, TraceStep
    from tracemarket.verifier import ConsistencyVerifier
    steps = [
        TraceStep(0, "action_a", "obs_a", "success"),
        TraceStep(1, "action_b", "obs_b", "success"),
    ]
    trace = AgentTrace("t", "agent", "task", steps)
    trace.steps[1].parent_id = "tampered_value"  # break the chain
    result = ConsistencyVerifier().verify(trace)
    assert result.verdict == "tampered", f"Expected 'tampered', got {result.verdict!r}"
    assert "hash_chain_integrity" in result.checks_failed

def _test_scrubber_removes_pii():
    from tracemarket.scrubber import PrivacyScrubber
    from tracemarket.trace import AgentTrace, TraceStep
    steps = [
        TraceStep(0, "Contact user@corp.example.com", "connected to 10.0.0.1", "success"),
        TraceStep(1, "SSN is 987-65-4321", "processed", "success"),
    ]
    trace = AgentTrace("t", "agent", "task", steps)
    original_action = trace.steps[0].action
    result = PrivacyScrubber().scrub(trace)
    assert result.replacements_count >= 3, f"Expected ≥3 replacements, got {result.replacements_count}"
    assert "email" in result.patterns_matched
    assert "ssn" in result.patterns_matched
    assert trace.steps[0].action == original_action, "Original trace must not be mutated"
    assert "user@corp.example.com" not in result.scrubbed_trace.steps[0].action

run("ConsistencyVerifier verifies a valid trace", _test_verifier_valid_trace)
run("ConsistencyVerifier detects tampered hash chain", _test_verifier_detects_tampered_chain)
run("PrivacyScrubber removes email, IP, SSN from trace steps", _test_scrubber_removes_pii)


# ── 4. Report formatters ──────────────────────────────────────────────────────

section("4. Report formatters")

def _test_to_json():
    from tracemarket.report import to_json
    from tracemarket.trace import AgentTrace, TraceStep
    from tracemarket.verifier import ConsistencyVerifier
    steps = [TraceStep(0, "action", "obs", "success")]
    trace = AgentTrace("t", "agent", "task", steps)
    result = ConsistencyVerifier().verify(trace)
    parsed = json.loads(to_json(trace=trace, result=result))
    assert parsed["verdict"] == "verified"
    assert "trace" in parsed
    assert "result" in parsed

def _test_to_markdown():
    from tracemarket.report import to_markdown
    from tracemarket.verifier import VerificationResult
    results = [
        VerificationResult("t1", "verified", ["hash_chain_integrity"], [], None, 100.0),
        VerificationResult("t2", "tampered", [], ["hash_chain_integrity"], None, 101.0),
    ]
    md = to_markdown(results)
    assert "tracemarket" in md
    assert "|" in md  # has table
    assert "tampered" in md
    assert "t1" in md

def _test_print_result():
    import io
    from rich.console import Console
    from tracemarket.report import print_result
    from tracemarket.verifier import VerificationResult
    buf = io.StringIO()
    con = Console(file=buf, highlight=False)
    result = VerificationResult("t1", "verified", ["check_a"], [], None, 100.0)
    print_result(result, console=con)
    output = buf.getvalue()
    assert "VERIFIED" in output or "verified" in output.lower()

run("to_json() returns valid JSON with verdict and trace", _test_to_json)
run("to_markdown() produces Markdown with table and verdicts", _test_to_markdown)
run("print_result() outputs verdict to console", _test_print_result)


# ── 5. CLI ────────────────────────────────────────────────────────────────────

section("5. CLI (tracemarket)")

def _test_cli_help():
    r = subprocess.run(
        [PYTHON, "-m", "tracemarket.cli", "--help"],
        capture_output=True, text=True
    )
    assert r.returncode == 0
    assert len(r.stdout) > 20, "Help output is empty"

def _test_cli_verify():
    from tracemarket.trace import AgentTrace, TraceStep
    with tempfile.TemporaryDirectory() as tmp:
        steps = [TraceStep(0, "action", "obs", "success")]
        trace = AgentTrace("t-cli", "agent", "task", steps)
        trace_file = Path(tmp) / "trace.json"
        trace_file.write_text(json.dumps(trace.to_dict()))
        r = subprocess.run(
            [PYTHON, "-m", "tracemarket.cli", "verify", str(trace_file)],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        assert r.returncode == 0, f"verify failed: {r.stderr}"

run("tracemarket --help returns 0", _test_cli_help)
run("tracemarket verify <valid trace> returns 0", _test_cli_verify)


# ── 6. FastAPI server ─────────────────────────────────────────────────────────

section("6. FastAPI server (tracemarket[api])")

def _test_api_import():
    from tracemarket.api import app
    assert app.title == "tracemarket API"

def _test_api_health():
    from fastapi.testclient import TestClient
    from tracemarket.api import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()

def _test_api_verify_and_scrub():
    from fastapi.testclient import TestClient
    from tracemarket.api import app
    from tracemarket.trace import AgentTrace, TraceStep
    client = TestClient(app)
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "traces.db")
        steps = [
            TraceStep(0, "Contact user@pii.com", "server 192.168.1.1", "success"),
        ]
        trace = AgentTrace("api-t", "agent", "task", steps)
        trace_dict = trace.to_dict()

        r_verify = client.post("/verify", json={"trace": trace_dict, "db": db})
        assert r_verify.status_code == 200
        assert r_verify.json()["verdict"] == "verified"

        r_scrub = client.post("/scrub", json={"trace": trace_dict})
        assert r_scrub.status_code == 200
        assert r_scrub.json()["replacements_count"] >= 2

run("tracemarket.api imports and app.title is correct", _test_api_import)
run("GET /health returns {status: ok, version: ...}", _test_api_health)
run("POST /verify + POST /scrub workflow", _test_api_verify_and_scrub)


# ── 7. MCP server ─────────────────────────────────────────────────────────────

section("7. MCP server (tracemarket[mcp])")

def _test_mcp_server_importable():
    import tracemarket.mcp_server as m
    assert hasattr(m, "run_server")

def _test_mcp_server_loads_cleanly():
    import tracemarket.mcp_server  # noqa: F401

run("mcp_server.py imports without error", _test_mcp_server_importable)
run("mcp_server module loads cleanly (no import-time crash)", _test_mcp_server_loads_cleanly)


# ── 8. Agent config files ─────────────────────────────────────────────────────

section("8. Agent config files (what a clone gives you)")

def _check_file_nonempty(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    assert p.stat().st_size > 50, f"File too small (likely empty): {rel}"

def _check_json_valid(rel: str) -> None:
    p = REPO_ROOT / rel
    assert p.exists(), f"Missing: {rel}"
    json.loads(p.read_text())

def _check_yaml_parseable(rel: str) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
        p = REPO_ROOT / rel
        assert p.exists(), f"Missing: {rel}"
        yaml.safe_load(p.read_text())
    except ImportError:
        content = (REPO_ROOT / rel).read_text()
        assert len(content) > 20, f"File appears empty: {rel}"

def _test_claude_commands():
    commands = list((REPO_ROOT / ".claude/commands").glob("*.md"))
    assert len(commands) >= 4, f"Expected ≥4 slash commands, found {len(commands)}"

def _test_openai_tools_valid():
    _check_json_valid("tools/openai-tools.json")
    tools = json.loads((REPO_ROOT / "tools/openai-tools.json").read_text())
    assert len(tools) >= 3
    assert all("function" in t for t in tools)

def _test_openapi_yaml_parseable():
    _check_yaml_parseable("openapi.yaml")

run("AGENTS.md exists and non-empty", lambda: _check_file_nonempty("AGENTS.md"))
run("CLAUDE.md exists and non-empty", lambda: _check_file_nonempty("CLAUDE.md"))
run("CODEX.md exists and non-empty", lambda: _check_file_nonempty("CODEX.md"))
run(".github/copilot-instructions.md exists", lambda: _check_file_nonempty(".github/copilot-instructions.md"))
def _test_cursor_rules():
    mdc_files = list((REPO_ROOT / ".cursor/rules").glob("*.mdc"))
    assert len(mdc_files) >= 1, f"Expected ≥1 .mdc file in .cursor/rules/, found none"

run(".cursor/rules/ has at least one .mdc file", _test_cursor_rules)
run(".windsurfrules exists", lambda: _check_file_nonempty(".windsurfrules"))
run(".aider.conf.yml exists", lambda: _check_file_nonempty(".aider.conf.yml"))
run(".continue/config.json is valid JSON", lambda: _check_json_valid(".continue/config.json"))
run(".claude/commands/ has ≥4 slash commands", _test_claude_commands)
run("tools/openai-tools.json is valid JSON with ≥3 tools", _test_openai_tools_valid)
run("openapi.yaml is parseable YAML", _test_openapi_yaml_parseable)


# ── 9. Docs site ──────────────────────────────────────────────────────────────

section("9. MkDocs documentation site")

def _test_mkdocs_yml():
    _check_file_nonempty("mkdocs.yml")
    content = (REPO_ROOT / "mkdocs.yml").read_text()
    assert "site_name" in content
    assert "material" in content

def _test_docs_pages():
    docs = list((REPO_ROOT / "docs").glob("*.md"))
    assert len(docs) >= 8, f"Expected ≥8 doc pages, found {len(docs)}"
    names = {p.name for p in docs}
    for required in ("index.md", "quickstart.md", "architecture.md", "api-reference.md"):
        assert required in names, f"Missing docs/{required}"

run("mkdocs.yml exists with site_name and material theme", _test_mkdocs_yml)
run("docs/ has ≥8 pages including index, quickstart, architecture, api-reference", _test_docs_pages)


# ── 10. examples/demo.py ─────────────────────────────────────────────────────

section("10. examples/demo.py end-to-end")

def _test_demo_runs():
    demo = REPO_ROOT / "examples" / "demo.py"
    assert demo.exists(), "examples/demo.py not found"
    r = subprocess.run(
        [PYTHON, str(demo)],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT)
    )
    if r.returncode != 0:
        raise AssertionError(f"demo.py exited {r.returncode}:\n{r.stderr[-500:]}")

run("examples/demo.py runs end-to-end without error", _test_demo_runs)


# ── Summary ───────────────────────────────────────────────────────────────────

total = len(passed) + len(failed)
print(f"\n{'═'*60}")
print(f"{BOLD}Results: {len(passed)}/{total} passed{RESET}")

if failed:
    print(f"{RED}Failed ({len(failed)}):{RESET}")
    for name, reason in failed:
        print(f"  {RED}✗{RESET} {name}")
        short = reason.split("\n")[0][:120]
        print(f"    {YELLOW}→ {short}{RESET}")
    print(f"\n{YELLOW}Tip: run with --verbose for full tracebacks{RESET}")
else:
    print(f"{GREEN}All {total} checks passed — tracemarket is ready to ship{RESET}")

print(f"{'═'*60}\n")
sys.exit(0 if not failed else 1)
