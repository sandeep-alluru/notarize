"""Export AgentTrace to CSV, timeline JSON, and compliance report formats."""

from __future__ import annotations

import csv
import datetime
import io
import json

from notarize.trace import AgentTrace

_KNOWN_STANDARDS = {"SOC2", "HIPAA", "GDPR"}


def to_csv(trace: AgentTrace) -> str:
    """Export trace as CSV: step_index,action,input_summary,output_summary,duration_ms,timestamp"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["step_index", "action", "input_summary", "output_summary", "duration_ms", "timestamp"]
    )

    steps = trace.steps
    for i, step in enumerate(steps):
        duration_ms = 0.0 if i == 0 else (step.timestamp - steps[i - 1].timestamp) * 1000.0

        input_summary = (step.observation or "")[:80]
        output_summary = (step.result or "")[:80]
        ts = datetime.datetime.fromtimestamp(
            step.timestamp, tz=datetime.timezone.utc
        ).isoformat()

        writer.writerow(
            [step.step_index, step.action, input_summary, output_summary, duration_ms, ts]
        )

    return buf.getvalue()


def to_timeline_json(trace: AgentTrace) -> str:
    """Export as JSON array suitable for timeline visualizations."""
    steps = trace.steps
    result = []

    for i, step in enumerate(steps):
        if i < len(steps) - 1:
            duration_ms = (steps[i + 1].timestamp - step.timestamp) * 1000.0
        else:
            duration_ms = 0.0

        start_time = datetime.datetime.fromtimestamp(
            step.timestamp, tz=datetime.timezone.utc
        ).isoformat()

        result.append(
            {
                "step_index": step.step_index,
                "action": step.action,
                "tool_name": step.tool_name,
                "start_time": start_time,
                "duration_ms": duration_ms,
                "status": step.result,
                "id": step.id,
            }
        )

    return json.dumps(result, indent=2)


def to_compliance_report(trace: AgentTrace, standard: str = "SOC2") -> str:
    """Generate a formal compliance report in markdown.

    Args:
        trace: The AgentTrace to report on.
        standard: One of 'SOC2', 'HIPAA', 'GDPR'.

    Returns:
        A markdown-formatted compliance report string.

    Raises:
        ValueError: If an unknown standard is specified.
    """
    if standard not in _KNOWN_STANDARDS:
        raise ValueError(
            f"Unknown compliance standard {standard!r}. Choose from: {sorted(_KNOWN_STANDARDS)}"
        )

    created_at_iso = datetime.datetime.fromtimestamp(
        trace.created_at, tz=datetime.timezone.utc
    ).isoformat()
    generated_at = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()

    lines: list[str] = []

    # Title
    lines.append(f"# {standard} Compliance Report — Trace {trace.trace_id}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Agent | {trace.agent_name} |")
    lines.append(f"| Task | {trace.task} |")
    lines.append(f"| Steps | {len(trace.steps)} |")
    lines.append(f"| Created At | {created_at_iso} |")
    lines.append(f"| Merkle Root | `{trace.merkle_root}` |")
    lines.append(f"| Trace ID | `{trace.trace_id}` |")
    lines.append("")

    # Standards-specific section
    if standard == "SOC2":
        lines.append("## SOC2 Trust Service Criteria")
        lines.append("")
        lines.append("### Availability")
        lines.append("")
        lines.append(f"- Trace recorded {len(trace.steps)} execution steps.")
        lines.append("- All steps are persisted and available for audit retrieval.")
        lines.append("")
        lines.append("### Confidentiality")
        lines.append("")
        lines.append(
            "- Trace data should be scrubbed of PII before storage using `notarize scrub`."
        )
        lines.append("- Access to the trace store should be restricted to authorised principals.")
        lines.append("")
        lines.append("### Processing Integrity")
        lines.append("")
        lines.append("- Chain integrity is enforced via the Merkle root of sorted step IDs.")
        lines.append(f"- Current Merkle root: `{trace.merkle_root}`.")
        lines.append("- Run `notarize verify` to confirm chain has not been tampered with.")

    elif standard == "HIPAA":
        lines.append("## HIPAA Compliance Notes")
        lines.append("")
        lines.append("### PHI Handling")
        lines.append("")
        lines.append("- Protected Health Information (PHI) must not appear in trace step fields.")
        lines.append("- Apply `notarize scrub` before storing or transmitting traces.")
        lines.append("")
        lines.append("### Access Controls")
        lines.append("")
        lines.append(
            "- The trace store (SQLite database) must be protected with file-system permissions."
        )
        lines.append("- Only authorised personnel should have read access to stored traces.")
        lines.append("")
        lines.append("### Audit Trail Completeness")
        lines.append("")
        lines.append(
            f"- This trace contains {len(trace.steps)} step(s), providing a complete audit trail."
        )
        lines.append(
            "- Merkle root verification ensures no steps have been added, removed, or altered."
        )
        lines.append(f"- Merkle root: `{trace.merkle_root}`.")

    elif standard == "GDPR":
        lines.append("## GDPR Compliance Notes")
        lines.append("")
        lines.append("### Data Minimisation")
        lines.append("")
        lines.append("- Traces should capture only the minimum data necessary for auditability.")
        lines.append("- Use `notarize scrub` to remove personal data before retention.")
        lines.append("")
        lines.append("### Purpose Limitation")
        lines.append("")
        lines.append(
            "- Traces are collected solely for agent execution auditability"
            " and compliance purposes."
        )
        lines.append("- Data must not be repurposed for unrelated processing activities.")
        lines.append("")
        lines.append("### Retention")
        lines.append("")
        lines.append("- Define and enforce a retention policy for stored traces.")
        lines.append("- Purge traces that are no longer required for their original purpose.")

    lines.append("")

    # Step table
    lines.append("## Step Summary")
    lines.append("")
    lines.append("| Step | Action | Tool | Result |")
    lines.append("|---|---|---|---|")
    for step in trace.steps:
        tool = step.tool_name or "—"
        lines.append(f"| {step.step_index} | {step.action} | {tool} | {step.result} |")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated at {generated_at} by notarize.*")

    return "\n".join(lines)
