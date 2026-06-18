"""CLI unit tests using Click's CliRunner (for code coverage)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from notarize.cli import main
from notarize.trace import AgentTrace, TraceStep


def _db(tmp_path: Path) -> str:
    return str(tmp_path / "traces.db")


def _trace_file(tmp_path: Path, trace_id: str = "t-cli") -> str:
    """Write a valid trace JSON file and return its path."""
    steps = [
        TraceStep(0, "tool_call:search", "found results", "success"),
        TraceStep(1, "tool_call:write", "wrote output", "success"),
    ]
    trace = AgentTrace(trace_id, "cli-agent", "do stuff", steps, created_at=0.0)
    path = tmp_path / f"{trace_id}.json"
    path.write_text(json.dumps(trace.to_dict()))
    return str(path)


def _pii_trace_file(tmp_path: Path) -> str:
    """Write a trace with PII in it."""
    steps = [
        TraceStep(0, "Email user@secret.com for info", "contacted alice@example.org", "success"),
    ]
    trace = AgentTrace("pii-trace", "agent", "contact user", steps, created_at=0.0)
    path = tmp_path / "pii.json"
    path.write_text(json.dumps(trace.to_dict()))
    return str(path)


# ── main group ────────────────────────────────────────────────────────────────


def test_main_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "verify" in result.output


def test_main_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0


# ── verify subcommand ─────────────────────────────────────────────────────────


def test_verify_valid_trace(tmp_path: Path) -> None:
    runner = CliRunner()
    trace_path = _trace_file(tmp_path)
    result = runner.invoke(main, ["--db", _db(tmp_path), "verify", trace_path])
    assert result.exit_code == 0
    assert "verified" in result.output.lower() or "VERIFIED" in result.output


def test_verify_json_format(tmp_path: Path) -> None:
    runner = CliRunner()
    trace_path = _trace_file(tmp_path)
    result = runner.invoke(main, ["--db", _db(tmp_path), "verify", trace_path, "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "result" in data


def test_verify_with_save(tmp_path: Path) -> None:
    runner = CliRunner()
    trace_path = _trace_file(tmp_path, "save-trace")
    result = runner.invoke(main, ["--db", _db(tmp_path), "verify", trace_path, "--save"])
    assert result.exit_code == 0
    assert "Saved" in result.output


def test_verify_bad_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json}")
    runner = CliRunner()
    result = runner.invoke(main, ["verify", str(bad_file)])
    assert result.exit_code != 0


def test_verify_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["verify", "--help"])
    assert result.exit_code == 0


# ── scrub subcommand ──────────────────────────────────────────────────────────


def test_scrub_stdout(tmp_path: Path) -> None:
    runner = CliRunner()
    trace_path = _pii_trace_file(tmp_path)
    result = runner.invoke(main, ["scrub", trace_path])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "trace_id" in data


def test_scrub_removes_email(tmp_path: Path) -> None:
    runner = CliRunner()
    trace_path = _pii_trace_file(tmp_path)
    result = runner.invoke(main, ["scrub", trace_path])
    assert result.exit_code == 0
    # PII should be gone from the scrubbed trace
    assert "user@secret.com" not in result.output
    assert "alice@example.org" not in result.output


def test_scrub_to_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    trace_path = _trace_file(tmp_path)
    out_path = str(tmp_path / "scrubbed.json")
    result = runner.invoke(main, ["scrub", trace_path, "-o", out_path])
    assert result.exit_code == 0
    assert Path(out_path).exists()


def test_scrub_bad_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    runner = CliRunner()
    result = runner.invoke(main, ["scrub", str(bad)])
    assert result.exit_code != 0


def test_scrub_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["scrub", "--help"])
    assert result.exit_code == 0


# ── log subcommand ────────────────────────────────────────────────────────────


def test_log_empty(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--db", _db(tmp_path), "log"])
    assert result.exit_code == 0
    assert "No traces" in result.output


def test_log_with_traces(tmp_path: Path) -> None:
    runner = CliRunner()
    db = _db(tmp_path)
    trace_path = _trace_file(tmp_path)
    runner.invoke(main, ["--db", db, "verify", trace_path, "--save"])
    result = runner.invoke(main, ["--db", db, "log"])
    assert result.exit_code == 0
    assert "t-cli" in result.output


def test_log_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["log", "--help"])
    assert result.exit_code == 0


# ── status subcommand ─────────────────────────────────────────────────────────


def test_status_empty_db(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--db", _db(tmp_path), "status"])
    assert result.exit_code == 0
    assert "Traces stored: 0" in result.output


def test_status_with_data(tmp_path: Path) -> None:
    runner = CliRunner()
    db = _db(tmp_path)
    trace_path = _trace_file(tmp_path)
    runner.invoke(main, ["--db", db, "verify", trace_path, "--save"])
    result = runner.invoke(main, ["--db", db, "status"])
    assert result.exit_code == 0
    assert "Traces stored: 1" in result.output


def test_status_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--help"])
    assert result.exit_code == 0
