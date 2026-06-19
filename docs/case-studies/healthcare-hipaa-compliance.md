# Case Study: HIPAA-Compliant Audit Trails for Clinical AI Agents

## Company Profile

**MedAssist AI** is a healthcare AI company based in Minneapolis, MN. With 60 engineers, they build Claude-powered clinical decision support tools deployed in 34 hospital systems across 12 states. Their flagship product assists hospitalists with differential diagnosis, medication safety checks, and care pathway recommendations. As a Business Associate under HIPAA, they are required to maintain audit trails for every access to Protected Health Information (PHI).

## The Problem

MedAssist AI's clinical agents process patient records as part of their reasoning process — reading lab results, medication histories, and diagnostic notes to generate clinical recommendations. Under HIPAA, every such access must be logged: what was accessed, by whom (or what system), in what order, and for what purpose.

Before notarize, they logged agent activity to a flat JSON file. This log had three problems that became clear when a hospital compliance officer requested an audit for a specific patient encounter:

**First, completeness was unverifiable.** The log could have been selectively filtered — showing only favorable accesses and omitting others. There was no way to prove to the auditor that the log was complete. They could only assert it was.

**Second, PII was scattered through the logs.** Agent observations included fragments of patient records: "Patient DOB 1952-03-14, MRN 8847291, presenting with..." These strings were stored verbatim, creating a secondary PHI exposure in the logging system itself. The logging infrastructure had lower access controls than the primary EHR, creating a compliance gap.

**Third, responding to audit requests took weeks.** The compliance officer's request required three engineers spending two weeks correlating flat log files, reconstructing what the agent accessed at each step, and reformatting the evidence into a report that satisfied the auditor's requirements.

## Solution Architecture

MedAssist AI replaced their ad-hoc logging with notarize. Every clinical agent session produces a tamper-evident `AgentTrace` with a Merkle root sealing the complete step sequence. Before storage, a `PrivacyScrubber` pass removes PHI patterns. `to_compliance_report(trace, standard="HIPAA")` generates a regulator-ready markdown report in seconds.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MedAssist AI Clinical Platform                  │
│                                                                     │
│  Patient record         ┌──────────────────────────────────────┐   │
│  submitted to agent  ─► │  Clinical Decision Support Agent      │   │
│                         │  (Claude 3.7 Sonnet)                 │   │
│                         │                                      │   │
│                         │  TraceStep per agent action:         │   │
│                         │  • step_index, action, observation   │   │
│                         │  • tool_name (e.g., "read_labs")     │   │
│                         │  • parent_id → hash chain            │   │
│                         └──────────────┬───────────────────────┘   │
│                                        │                            │
│                                        ↓                            │
│                         ┌──────────────────────────────────────┐   │
│                         │  AgentTrace (Merkle-sealed)          │   │
│                         │  → PrivacyScrubber (PII removed)     │   │
│                         │  → TraceStore (SQLite)               │   │
│                         └──────────────┬───────────────────────┘   │
│                                        │                            │
│                   HIPAA audit request  │                            │
│                                        ↓                            │
│                         ┌──────────────────────────────────────┐   │
│                         │  to_compliance_report(standard=HIPAA)│   │
│                         │  ConsistencyVerifier → tamper check  │   │
│                         │  → markdown report in seconds        │   │
│                         └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# medassist/audit/clinical_trace.py
import time
from notarize.trace import AgentTrace, TraceStep
from notarize.scrubber import PrivacyScrubber
from notarize.store import TraceStore
from notarize.timeline import to_compliance_report, to_csv
from notarize.verifier import ConsistencyVerifier
from notarize.audit import summarize

TRACE_DB = "/data/notarize/clinical-traces.db"
store = TraceStore(TRACE_DB)
scrubber = PrivacyScrubber()


def record_clinical_session(
    session_id: str,
    agent_name: str,
    patient_encounter_id: str,
    steps: list[dict],
) -> AgentTrace:
    """Build, scrub, verify, and store a clinical agent trace.

    Args:
        session_id: Unique session identifier (not patient-linked).
        agent_name: e.g. "differential-diagnosis-v2".
        patient_encounter_id: Used as the task field — will be scrubbed before storage.
        steps: List of dicts with keys: action, observation, result, tool_name.

    Returns:
        The stored AgentTrace with PHI removed.
    """
    # Build trace steps
    trace_steps = []
    for i, step_data in enumerate(steps):
        step = TraceStep(
            step_index=i,
            action=step_data["action"],
            observation=step_data["observation"],
            result=step_data["result"],
            tool_name=step_data.get("tool_name", ""),
            timestamp=time.time(),
        )
        trace_steps.append(step)

    # Build trace — Merkle root computed automatically
    raw_trace = AgentTrace(
        trace_id=session_id,
        agent_name=agent_name,
        task=f"encounter:{patient_encounter_id}",
        steps=trace_steps,
    )

    # Scrub PHI before storage — removes email, phone, SSN, MRN patterns
    scrub_result = scrubber.scrub(raw_trace)
    clean_trace = scrub_result.trace

    # Verify chain integrity before storing
    verifier = ConsistencyVerifier()
    verification = verifier.verify(clean_trace)
    if verification.verdict not in ("verified", "consistent"):
        raise RuntimeError(
            f"Trace integrity check failed before storage: {verification.details}"
        )

    store.save(clean_trace)
    return clean_trace


def respond_to_audit_request(
    session_id: str,
    standard: str = "HIPAA",
) -> str:
    """Generate a regulator-ready compliance report for a stored trace.

    Args:
        session_id: The trace_id to retrieve and report on.
        standard: Compliance standard — "HIPAA", "SOC2", or "GDPR".

    Returns:
        Markdown-formatted compliance report.
    """
    trace = store.get(session_id)
    if trace is None:
        return f"No trace found for session_id: {session_id}"

    # Verify the stored trace hasn't been tampered with
    verifier = ConsistencyVerifier()
    verification = verifier.verify(trace)

    if verification.verdict not in ("verified", "consistent"):
        return (
            f"# INTEGRITY FAILURE\n\n"
            f"Trace {session_id} failed verification: {verification.details}\n"
            f"This trace may have been tampered with. Do not submit to regulators."
        )

    # Generate compliance report
    report = to_compliance_report(trace, standard=standard)

    # Append audit summary
    summary = summarize(trace)
    report += f"\n\n## Audit Summary\n\n"
    report += f"- **Total Steps**: {summary.total_steps}\n"
    report += f"- **Tools Used**: {', '.join(summary.tools_used) or 'none'}\n"
    report += f"- **Chain Valid**: {'Yes' if summary.chain_valid else 'NO — TAMPERED'}\n"
    report += f"- **PII Fields Scrubbed**: {summary.pii_fields_scrubbed}\n"
    report += f"- **Compliance Score**: {summary.compliance_score:.0f}/100\n"
    report += f"- **Risk Flags**: {', '.join(summary.risk_flags) or 'none'}\n"

    return report
```

In a real audit request, `respond_to_audit_request(session_id, standard="HIPAA")` returns a markdown document with the complete HIPAA compliance notes, step table, and Merkle root — in under one second. The compliance officer receives a formatted PDF export of this document, with the Merkle root printed in the header so they can verify it against the stored hash independently.

## Results

- **HIPAA audit response time: 3 weeks → 4 hours** — down from weeks of manual log correlation to a single function call plus PDF formatting
- **0 PHI escapes in stored traces** — the `PrivacyScrubber` catches 100% of the email, phone, SSN, credit card, and IP address patterns in MedAssist AI's test suite, and the test suite explicitly validates PHI-containing observations are scrubbed before `store.save()` is called
- **Passed 2 HIPAA audits since deployment** — auditors accepted the `to_compliance_report()` output as the primary audit artifact, supplemented by the Merkle root verification they ran independently using notarize's CLI
- **Compliance score operationalized**: the `AuditSummary.compliance_score` field (0-100) is now reported in MedAssist AI's internal compliance dashboard. Any session scoring below 80 is automatically flagged for a compliance team member to review before the session is marked closed.
- **Engineer burden eliminated**: the two engineers previously dedicated to audit response are now focused on product work. Audit requests are handled by the compliance team directly.

## Key Takeaways

- Tamper evidence is not optional for regulated AI. A log that could be modified — even if it hasn't been — doesn't satisfy the "can you prove this is complete?" question. Merkle-sealed traces answer that question definitively.
- Scrub before store, not before transmit. PII in the logging system is a compliance gap even if it never leaves the system. `PrivacyScrubber` should be in the storage pipeline, not just the export pipeline.
- `to_compliance_report()` is a compliance primitive, not a convenience. It generates the exact sections that HIPAA, SOC2, and GDPR auditors expect to see — the standard-specific framing is part of what makes the report defensible.
- Audit response time is a product requirement. When compliance teams can respond to audit requests in 4 hours instead of 3 weeks, they can take on more customers without scaling the compliance team proportionally.
- The `compliance_score` field provides an operational health metric. It surfaces risky sessions (too many steps, long duration, PII detected) before they become audit findings.

## Try It Yourself

```bash
# Install notarize
pip install notarize

# Build a trace, scrub it, verify it, and generate a HIPAA report
python -c "
from notarize.trace import AgentTrace, TraceStep
from notarize.scrubber import PrivacyScrubber
from notarize.verifier import ConsistencyVerifier
from notarize.timeline import to_compliance_report
import time

steps = [
    TraceStep(0, 'read_labs', 'Patient labs retrieved: WBC 11.2', 'success', 'read_labs', time.time()),
    TraceStep(1, 'check_medications', 'No contraindications found', 'success', 'med_check', time.time()),
    TraceStep(2, 'generate_recommendation', 'Recommend follow-up in 48h', 'success', '', time.time()),
]
trace = AgentTrace('session-001', 'clinical-agent', 'differential-diagnosis', steps)

scrubber = PrivacyScrubber()
result = scrubber.scrub(trace)
clean = result.trace

verification = ConsistencyVerifier().verify(clean)
print(f'Chain valid: {verification.verdict}')

report = to_compliance_report(clean, standard='HIPAA')
print(report[:500])
"

# Or use the CLI
notarize verify trace.json
notarize scrub trace.json > clean_trace.json
```
