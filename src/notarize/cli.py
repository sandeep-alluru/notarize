"""Command-line interface for notarize."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from notarize.audit import summarize
from notarize.report import print_result, to_json
from notarize.scrubber import PrivacyScrubber
from notarize.store import TraceStore
from notarize.trace import AgentTrace
from notarize.verifier import ConsistencyVerifier


def _store(ctx: click.Context) -> TraceStore:
    """Return a TraceStore from the context or default path."""
    db_path = ctx.obj.get("db") if ctx.obj else ".notarize/traces.db"
    return TraceStore(db_path)


@click.group()
@click.version_option(package_name="notarize")
@click.option(
    "--db",
    default=".notarize/traces.db",
    show_default=True,
    help="Path to the notarize database.",
    envvar="NOTARIZE_DB",
)
@click.pass_context
def main(ctx: click.Context, db: str) -> None:
    """Canonical trace format and verifier for agent execution attestation.

    notarize records, verifies, and audits agent execution traces
    for EU AI Act compliance and forensic analysis.
    """
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["rich", "json"]),
    default="rich",
    show_default=True,
)
@click.option("--save", is_flag=True, default=False, help="Save result to the database.")
@click.pass_context
def verify(ctx: click.Context, file: str, fmt: str, save: bool) -> None:
    """Verify a JSON trace file for internal consistency.

    \b
    Examples:
      notarize verify trace.json
      notarize verify trace.json --format json
      notarize verify trace.json --save
    """
    try:
        data = json.loads(Path(file).read_text())
        trace = AgentTrace.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise click.ClickException(f"Failed to parse trace file: {exc}") from exc

    verifier = ConsistencyVerifier()
    result = verifier.verify(trace)

    if fmt == "rich":
        print_result(result)
    else:
        click.echo(to_json(trace=trace, result=result))

    if save:
        with _store(ctx) as store:
            store.save_trace(trace)
            store.save_result(result)
            click.echo(f"Saved trace {trace.trace_id!r} and result {result.id!r}.")

    if result.verdict in ("tampered", "invalid"):
        sys.exit(1)


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    default="-",
    help="Output file (default: stdout).",
)
@click.pass_context
def scrub(ctx: click.Context, file: str, output: str) -> None:
    """Scrub PII from a trace file and output the scrubbed JSON.

    \b
    Examples:
      notarize scrub trace.json
      notarize scrub trace.json -o scrubbed.json
    """
    try:
        data = json.loads(Path(file).read_text())
        trace = AgentTrace.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise click.ClickException(f"Failed to parse trace file: {exc}") from exc

    scrubber = PrivacyScrubber()
    result = scrubber.scrub(trace)

    scrubbed_json = json.dumps(result.scrubbed_trace.to_dict(), indent=2)

    if output == "-":
        click.echo(scrubbed_json)
    else:
        Path(output).write_text(scrubbed_json)
        click.echo(
            f"Scrubbed {result.replacements_count} replacement(s) "
            f"({', '.join(result.patterns_matched) or 'none'}) → {output}"
        )


@main.command("log")
@click.pass_context
def log_cmd(ctx: click.Context) -> None:
    """List all stored traces.

    \b
    Examples:
      notarize log
    """
    with _store(ctx) as store:
        traces = store.list_traces()

    if not traces:
        click.echo("No traces stored.")
        return

    click.echo(f"{'Trace ID':<20}  {'Agent':<20}  {'Steps':>5}  {'Task'}")
    click.echo("-" * 72)
    for trace in traces:
        task_preview = trace.task[:35] + "…" if len(trace.task) > 35 else trace.task
        click.echo(
            f"{trace.trace_id:<20}  {trace.agent_name:<20}  {len(trace.steps):>5}  {task_preview}"
        )


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show store info.

    \b
    Examples:
      notarize status
    """
    with _store(ctx) as store:
        traces = store.list_traces()
        results = store.list_results()

    click.echo(f"Database: {ctx.obj.get('db', '.notarize/traces.db')}")
    click.echo(f"Traces stored: {len(traces)}")
    click.echo(f"Verification results stored: {len(results)}")

    if results:
        verdicts: dict[str, int] = {}
        for r in results:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        for verdict, count in sorted(verdicts.items()):
            click.echo(f"  {verdict}: {count}")


@main.command("audit")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["rich", "json"]),
    default="rich",
    show_default=True,
)
@click.pass_context
def audit_cmd(ctx: click.Context, file: str, fmt: str) -> None:
    """Show an audit summary for a trace file.

    \b
    Examples:
      notarize audit trace.json
      notarize audit trace.json --format json
    """
    try:
        data = json.loads(Path(file).read_text())
        trace = AgentTrace.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise click.ClickException(f"Failed to parse trace file: {exc}") from exc

    summary = summarize(trace)

    if fmt == "json":
        click.echo(
            json.dumps(
                {
                    "session_id": summary.session_id,
                    "agent_id": summary.agent_id,
                    "total_steps": summary.total_steps,
                    "duration_ms": summary.duration_ms,
                    "tools_used": summary.tools_used,
                    "pii_fields_scrubbed": summary.pii_fields_scrubbed,
                    "chain_valid": summary.chain_valid,
                    "risk_flags": summary.risk_flags,
                    "compliance_score": summary.compliance_score,
                },
                indent=2,
            )
        )
    else:
        score = summary.compliance_score
        if score >= 80:
            score_str = click.style(f"{score:.1f}", fg="green", bold=True)
        elif score >= 50:
            score_str = click.style(f"{score:.1f}", fg="yellow", bold=True)
        else:
            score_str = click.style(f"{score:.1f}", fg="red", bold=True)

        chain_str = (
            click.style("✓ valid", fg="green")
            if summary.chain_valid
            else click.style("✗ broken", fg="red")
        )

        click.echo(f"Session ID      : {summary.session_id}")
        click.echo(f"Agent           : {summary.agent_id}")
        click.echo(f"Total steps     : {summary.total_steps}")
        click.echo(f"Duration        : {summary.duration_ms:.1f} ms")
        click.echo(f"Tools used      : {', '.join(summary.tools_used) or '(none)'}")
        click.echo(f"PII scrubbed    : {summary.pii_fields_scrubbed}")
        click.echo(f"Chain           : {chain_str}")
        click.echo(f"Risk flags      : {', '.join(summary.risk_flags) or '(none)'}")
        click.echo(f"Compliance score: {score_str} / 100")


if __name__ == "__main__":
    main()
