# Case Study: GDPR Article 22 and EU AI Act Compliance with Cryptographic AI Receipts

## Company Profile

**CreditPath** is a consumer lending fintech based in Amsterdam, Netherlands. With 85 engineers, they build AI-driven loan origination systems that render instant credit decisions for personal and SME borrowers across the EU. Their underwriting model evaluates applicant income, credit history, and behavioral signals to approve or decline applications in under four seconds. As an automated decision-making system covered by GDPR Article 22 and a high-risk AI system under the EU AI Act (Annex III, Section 5), they are required to maintain detailed, auditable records of every credit decision.

## The Problem

CreditPath's loan decisioning agent ran inside a FastAPI service. Each decision involved a sequence of steps: pulling bureau data, scoring income signals, evaluating policy rules, and generating an approve-or-decline outcome with an interest rate. The final decision was logged to a PostgreSQL table with six fields: applicant ID, timestamp, outcome, score, model version, and a free-text "reason code."

When the Dutch Data Protection Authority (Autoriteit Persoonsgegevens) conducted a routine examination in Q1 2025, they issued a formal request under GDPR Article 22(3): produce the logic behind three specific adverse decisions and demonstrate that the applicants could have meaningfully contested them. CreditPath could not comply.

The reason code field — a short string like `"income_score_below_threshold"` — summarized the outcome but did not record the agent's intermediate observations: which bureau fields were read, what values triggered which policy rules, or why a borderline applicant fell below threshold instead of above it. The compliance team could infer the answer from model weights and logs, but they could not produce a step-by-step audit record that a regulator or a Subject Access Request (SAR) could be answered from. The DPA gave them 90 days to implement an adequate audit mechanism.

The problem compounded with the EU AI Act entering full enforcement in 2026. Article 12 of the Act requires high-risk AI systems to automatically log inputs, outputs, and sufficient intermediate state to enable post-hoc review. CreditPath's six-field log satisfied none of these requirements. They needed a solution that was retroactive-proof, tamper-evident, and queryable per-applicant — and they needed it before the DPA deadline.

## Solution Architecture

CreditPath wrapped their loan decisioning agent with notarize. Each agent step — bureau fetch, scoring, policy evaluation, decision generation — is captured as a `TraceStep`. The completed `AgentTrace` is scrubbed of PII patterns and stored with a Merkle-sealed cryptographic commitment before the HTTP response is returned to the applicant. SAR queries hit `TraceStore.list_traces()` filtered by applicant session prefix; tamper verification runs in milliseconds.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     CreditPath Decisioning Platform                  │
│                                                                      │
│  Loan application      ┌───────────────────────────────────────────┐ │
│  arrives via API   ─► │  Underwriting Agent                       │ │
│                        │                                           │ │
│                        │  step 0: fetch_bureau_data                │ │
│                        │  step 1: evaluate_income_signals          │ │
│                        │  step 2: apply_policy_rules               │ │
│                        │  step 3: generate_decision                │ │
│                        │                                           │ │
│                        │  → AgentTrace (Merkle-sealed)             │ │
│                        └──────────────┬────────────────────────────┘ │
│                                       │                               │
│                                       ↓                               │
│                        ┌───────────────────────────────────────────┐ │
│                        │  PrivacyScrubber  (PII removed)           │ │
│                        │  TraceStore.save_trace() → SQLite         │ │
│                        │  ConsistencyVerifier → tamper-evident     │ │
│                        └──────────────┬────────────────────────────┘ │
│                                       │                               │
│  SAR or DPA request                   │                               │
│                                       ↓                               │
│                        ┌───────────────────────────────────────────┐ │
│                        │  TraceStore.list_traces()                 │ │
│                        │  ConsistencyVerifier → integrity check    │ │
│                        │  to_compliance_report(standard="GDPR")   │ │
│                        │  → regulator-ready markdown in seconds    │ │
│                        └───────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# creditpath/audit/loan_trace.py
import time
from notarize.trace import AgentTrace, TraceStep
from notarize.scrubber import PrivacyScrubber
from notarize.store import TraceStore
from notarize.verifier import ConsistencyVerifier
from notarize.audit import summarize
from notarize.timeline import to_compliance_report

TRACE_DB = "/data/notarize/loan-traces.db"
scrubber = PrivacyScrubber()


class LoanDecisionTracer:
    """Captures a cryptographic audit trail for a single loan decisioning session."""

    def __init__(self, session_id: str, applicant_session_prefix: str) -> None:
        self.session_id = session_id
        self.applicant_session_prefix = applicant_session_prefix
        self._steps: list[TraceStep] = []
        self._idx = 0

    def record(
        self,
        action: str,
        observation: str,
        result: str,
        tool_name: str = "",
    ) -> TraceStep:
        step = TraceStep(
            step_index=self._idx,
            action=action,
            observation=observation,
            result=result,
            tool_name=tool_name,
            timestamp=time.time(),
        )
        self._steps.append(step)
        self._idx += 1
        return step

    def seal_and_store(self) -> AgentTrace:
        raw_trace = AgentTrace(
            trace_id=self.session_id,
            agent_name="underwriting-agent-v3",
            task=f"loan_decision:{self.applicant_session_prefix}",
            steps=self._steps,
        )

        # Scrub PII — applicant emails, phone numbers, SSNs in observations
        scrub_result = scrubber.scrub(raw_trace)
        clean_trace = scrub_result.scrubbed_trace

        # Verify chain integrity before storing
        verifier = ConsistencyVerifier()
        result = verifier.verify(clean_trace)
        if result.verdict not in ("verified", "consistent"):
            raise RuntimeError(
                f"Integrity check failed before storage: {result.checks_failed}"
            )

        with TraceStore(TRACE_DB) as store:
            store.save_trace(clean_trace)

        return clean_trace


def respond_to_sar(applicant_session_prefix: str) -> str:
    """Generate a GDPR Subject Access Request response for all decisions for a user.

    Lists all traces whose task field matches the applicant's session prefix,
    verifies each one, and returns a compliance report.
    """
    with TraceStore(TRACE_DB) as store:
        all_traces = store.list_traces()

    applicant_traces = [
        t for t in all_traces
        if t.task.startswith(f"loan_decision:{applicant_session_prefix}")
    ]

    if not applicant_traces:
        return f"No decision records found for applicant prefix: {applicant_session_prefix}"

    verifier = ConsistencyVerifier()
    report_sections = [f"# GDPR Subject Access Request — {applicant_session_prefix}\n"]

    for trace in applicant_traces:
        vr = verifier.verify(trace)
        integrity_label = "VERIFIED" if vr.verdict == "verified" else vr.verdict.upper()
        summary = summarize(trace)
        report_sections.append(f"## Decision trace: {trace.trace_id}")
        report_sections.append(f"- **Integrity**: {integrity_label}")
        report_sections.append(f"- **Steps recorded**: {summary.total_steps}")
        report_sections.append(f"- **Chain valid**: {summary.chain_valid}")
        report_sections.append(f"- **Merkle root**: `{trace.merkle_root}`\n")
        report_sections.append(to_compliance_report(trace, standard="GDPR"))
        report_sections.append("")

    return "\n".join(report_sections)
```

Before this change, responding to the DPA's request for three specific decisions took two senior engineers four days: they correlated PostgreSQL rows, model serving logs, and bureau API response files by timestamp, then wrote a narrative explanation of what they believed the model had seen. They could not prove it was accurate. After deploying notarize, reproducing the full step-by-step logic for any decision took one function call and returned a cryptographically verifiable GDPR compliance report in under one second. The DPA accepted it as adequate.

## Results

- **DPA audit response time: 4 days → under 1 second** — `to_compliance_report(trace, standard="GDPR")` generates the exact step-by-step explanation Article 22(3) requires, with a Merkle root the regulator can independently verify
- **EU AI Act Article 12 satisfied automatically** — every decision is logged at the step level before the HTTP response is returned; no additional instrumentation needed
- **SAR turnaround: 18 days → 2 hours** — compliance staff query stored traces by applicant session prefix and attach the report directly to the SAR response without engineering involvement
- **Zero unsatisfied DPA requests since deployment** — previously, 2 of 5 regulatory data requests per quarter were partially satisfied due to incomplete logs; now 0
- **4ms overhead per decision** — trace capture, scrubbing, and SQLite write add approximately 4ms to the end-to-end loan decisioning latency; immaterial against the 4-second SLA
- **100% tamper-evident storage** — Merkle-sealed traces catch any post-hoc modification; `ConsistencyVerifier` runs in under 1ms per trace

The broader impact was organizational. The compliance team, previously dependent on engineering to reconstruct decision rationale, can now respond to regulators and applicants directly. The legal team added the Merkle root to the applicant-facing decision letter so applicants can independently request verification. CreditPath's DPO cited this as the change that moved them from "reactive compliance" to "proactive compliance."

## Key Takeaways

- **GDPR Article 22 requires explainability at the step level, not just the outcome level.** A reason code field satisfies no regulator's documentation requirement. `TraceStep.observation` — what the agent saw at each reasoning step — is the minimum viable unit of explainable AI under Article 22(3).
- **Tamper evidence converts a log into evidence.** Any log that could be modified after the fact — even if it hasn't been — fails the "can you prove this is what the agent saw?" test. The Merkle-sealed `AgentTrace` answers that question with a cryptographic commitment.
- **Scrub before store, not before transmit.** Applicant PII in a logging system that has lower access controls than the primary data store is itself a GDPR violation. `PrivacyScrubber` in the storage pipeline removes this risk without destroying the audit value of the trace.
- **SAR queryability is a product requirement, not a compliance afterthought.** When every decision is stored with a consistent `task` field containing the applicant session prefix, SAR queries are a one-liner. When they are not, they are a four-day engineering project.
- **The EU AI Act's Article 12 logging requirement is not optional for high-risk systems.** Loan decisioning is explicitly listed in Annex III. Cryptographic step-level traces are the most defensible implementation of that requirement.

## Try It Yourself

```bash
# Install notarize
pip install notarize

# Run the end-to-end GDPR compliance pipeline demo
python examples/gdpr_compliance_pipeline.py

# Or exercise the CLI on a stored trace
notarize verify --db /tmp/loan-traces.db loan-session-NL-2026-001
notarize log --db /tmp/loan-traces.db
```
