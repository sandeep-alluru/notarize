"""Rich terminal, JSON, and Markdown output formatters for notarize."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from notarize.trace import AgentTrace
from notarize.verifier import VerificationResult

_console = Console()


def _truncate(text: str, max_len: int = 72) -> str:
    """Truncate text to max_len with ellipsis."""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def print_result(result: VerificationResult, console: Console | None = None) -> None:
    """Print a VerificationResult to the terminal using Rich.

    Args:
        result: The VerificationResult to display.
        console: Optional Rich Console to write to (defaults to stdout).
    """
    con = console or _console

    verdict = result.verdict.upper()
    if result.verdict == "verified":
        style = "bold green"
        icon = "✓"
    elif result.verdict == "consistent":
        style = "bold yellow"
        icon = "~"
    elif result.verdict == "tampered":
        style = "bold red"
        icon = "✗"
    else:
        style = "bold red"
        icon = "!"

    con.print(
        Panel(
            f"[{style}]{icon} {verdict}[/{style}]  trace_id={result.trace_id!r}",
            expand=False,
            border_style="green" if result.verdict == "verified" else "red",
        )
    )

    if result.checks_passed:
        con.print("[green]Checks passed:[/green]")
        for check in result.checks_passed:
            con.print(f"  [green]✓[/green] {check}")

    if result.checks_failed:
        con.print("[red]Checks failed:[/red]")
        for check in result.checks_failed:
            con.print(f"  [red]✗[/red] {check}")

    if result.error:
        con.print(f"[red]Error:[/red] {result.error}")

    con.print()


def print_trace(trace: AgentTrace, console: Console | None = None) -> None:
    """Print an AgentTrace summary to the terminal using Rich.

    Args:
        trace: The AgentTrace to display.
        console: Optional Rich Console to write to (defaults to stdout).
    """
    con = console or _console

    con.print(
        Panel(
            f"[bold]AgentTrace[/bold]  [dim]{trace.id}[/dim]\n"
            f"trace_id={trace.trace_id!r}  agent={trace.agent_name!r}\n"
            f"task={_truncate(trace.task, 60)!r}",
            expand=False,
        )
    )

    if not trace.steps:
        con.print("[dim]No steps.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", width=3)
    table.add_column("Action", width=25)
    table.add_column("Result", width=10)
    table.add_column("Tool", width=15)

    for step in trace.steps:
        result_style = "green" if step.result == "success" else "red"
        table.add_row(
            str(step.step_index),
            _truncate(step.action, 25),
            Text(step.result, style=result_style),
            step.tool_name or "-",
        )

    con.print(table)
    con.print(f"[dim]Merkle root: {trace.merkle_root}[/dim]")
    con.print()


def to_json(
    trace: AgentTrace | None = None,
    result: VerificationResult | None = None,
) -> str:
    """Serialize a trace and/or verification result to JSON.

    Args:
        trace: Optional AgentTrace to include.
        result: Optional VerificationResult to include.

    Returns:
        JSON string.
    """
    data: dict[str, Any] = {}
    if trace is not None:
        data["trace"] = trace.to_dict()
    if result is not None:
        data["result"] = result.to_dict()
        data["verdict"] = result.verdict
    return json.dumps(data, indent=2)


def to_markdown(results: list[VerificationResult]) -> str:
    """Generate a Markdown report from a list of VerificationResult objects.

    Args:
        results: List of VerificationResult objects.

    Returns:
        Markdown string suitable for posting as a PR comment.
    """
    if not results:
        return "## notarize verification report\n\nNo verification results to report.\n"

    verified = [r for r in results if r.verdict == "verified"]
    tampered = [r for r in results if r.verdict == "tampered"]
    invalid = [r for r in results if r.verdict == "invalid"]

    status = "🟢" if not tampered and not invalid else "🔴"

    lines = [
        "## notarize verification report",
        "",
        f"{status} **{len(verified)}/{len(results)} verified** — "
        f"{len(tampered)} tampered, {len(invalid)} invalid.",
        "",
        "| Trace ID | Verdict | Checks Passed | Checks Failed |",
        "|----------|---------|---------------|---------------|",
    ]

    for result in results[:20]:
        verdict_badge = {
            "verified": "✅ verified",
            "consistent": "⚠️ consistent",
            "tampered": "❌ tampered",
            "invalid": "💥 invalid",
        }.get(result.verdict, result.verdict)
        lines.append(
            f"| `{result.trace_id}` | {verdict_badge} "
            f"| {len(result.checks_passed)} "
            f"| {len(result.checks_failed)} |"
        )

    if len(results) > 20:
        lines.append(f"| … | *{len(results) - 20} more* | | |")

    lines += [
        "",
        "<details><summary>Full JSON</summary>",
        "",
        "```json",
        json.dumps([r.to_dict() for r in results], indent=2),
        "```",
        "",
        "</details>",
        "",
        "*Generated by [notarize](https://github.com/sandeep-alluru/notarize)*",
    ]
    return "\n".join(lines)
