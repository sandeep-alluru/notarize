"""
notarize demo — canonical trace format and verifier for agent execution attestation.

Run with: python examples/demo.py
"""

import shutil
import tempfile

from notarize.report import print_result, print_trace, to_json, to_markdown
from notarize.scrubber import PrivacyScrubber
from notarize.store import TraceStore
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier

tmp = tempfile.mkdtemp()

try:
    print("=== notarize demo ===\n")

    # Step 1: Build an agent execution trace
    steps = [
        TraceStep(
            step_index=0,
            action="tool_call:search",
            observation="Found 5 relevant documents about EU AI Act Article 13",
            result="success",
            tool_name="search",
        ),
        TraceStep(
            step_index=1,
            action="tool_call:read",
            observation="Read contract.pdf — 42 pages, identifies 3 high-risk AI systems",
            result="success",
            tool_name="read",
        ),
        TraceStep(
            step_index=2,
            action="tool_call:analyze",
            observation="Risk analysis complete: systems require conformity assessment",
            result="success",
            tool_name="analyze",
        ),
        TraceStep(
            step_index=3,
            action="tool_call:write",
            observation="Compliance report generated and saved",
            result="success",
            tool_name="write",
        ),
    ]

    trace = AgentTrace(
        trace_id="audit-2024-eu-act-001",
        agent_name="compliance-auditor-v1",
        task="Review AI systems for EU AI Act compliance",
        steps=steps,
    )

    print(f"Created trace: {trace.trace_id}")
    print(f"  Agent: {trace.agent_name}")
    print(f"  Steps: {len(trace.steps)}")
    print(f"  Merkle root: {trace.merkle_root}")
    print(f"  Trace ID hash: {trace.id}\n")

    # Step 2: Verify the trace
    print("=== Verification ===\n")
    verifier = ConsistencyVerifier()
    result = verifier.verify(trace)

    print(f"Verdict: {result.verdict}")
    print(f"Checks passed: {', '.join(result.checks_passed)}")
    print(f"Checks failed: {result.checks_failed}\n")

    # Step 3: PII scrubbing demo
    print("=== PII Scrubbing ===\n")
    pii_steps = [
        TraceStep(
            0,
            "tool_call:contact",
            "Emailed compliance@law-firm.example.com about case 2024-001",
            "success",
        ),
        TraceStep(
            1,
            "tool_call:log",
            "Logged access from IP 203.0.113.42, user SSN 123-45-6789",
            "success",
        ),
    ]
    pii_trace = AgentTrace(
        trace_id="pii-demo-001",
        agent_name="data-processor",
        task="Process customer data",
        steps=pii_steps,
    )

    scrubber = PrivacyScrubber()
    scrub_result = scrubber.scrub(pii_trace)
    print(f"Original action: {pii_trace.steps[0].action}")
    print(f"Scrubbed action: {scrub_result.scrubbed_trace.steps[0].action}")
    print(f"Replacements: {scrub_result.replacements_count}")
    print(f"Patterns matched: {', '.join(scrub_result.patterns_matched)}\n")

    # Step 4: Store and retrieve
    print("=== Store & Retrieve ===\n")
    db_path = f"{tmp}/traces.db"
    with TraceStore(db_path) as store:
        store.save_trace(trace)
        store.save_result(result)

        retrieved = store.get_trace("audit-2024-eu-act-001")
        assert retrieved is not None, "Trace should be retrievable"
        print(f"Stored and retrieved trace: {retrieved.trace_id}")

        all_traces = store.list_traces()
        print(f"Total traces in store: {len(all_traces)}\n")

    # Step 5: Tamper detection demo
    print("=== Tamper Detection ===\n")
    tampered_trace = AgentTrace.from_dict(trace.to_dict())
    tampered_trace.steps[1].action = "TAMPERED_ACTION"
    tampered_trace.steps[1].parent_id = "0000000000000000"

    tamper_result = verifier.verify(tampered_trace)
    print(f"Tampered trace verdict: {tamper_result.verdict}")
    print(f"Failed checks: {', '.join(tamper_result.checks_failed)}\n")

    # Step 6: Formatters
    print("=== Formatters ===\n")
    md = to_markdown([result, tamper_result])
    print("Markdown report (first 3 lines):")
    print("\n".join(md.split("\n")[:3]))
    print()

    print("JSON output (verdict field):")
    import json

    parsed = json.loads(to_json(trace=trace, result=result))
    print(f"  verdict: {parsed['verdict']}")
    print(f"  trace.trace_id: {parsed['trace']['trace_id']}\n")

    print("=== Demo complete ===")

finally:
    shutil.rmtree(tmp)
