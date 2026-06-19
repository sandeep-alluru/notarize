"""agent_behavior_forensics.py

Forensic investigation: a CustomerServiceAgent issued a $15 refund instead
of $150.  We use notarize to walk the trace, pinpoint the exact step that
introduced the error, and produce a root-cause report.
"""

import os
import tempfile

from notarize.store import TraceStore
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier

# ---------------------------------------------------------------------------
# 1. Reconstruct the incident trace
# ---------------------------------------------------------------------------

steps = [
    TraceStep(
        step_index=0,
        action="lookup_order",
        observation="order ORD-9921 found: original_price=$150.00, quantity=1",
        result="success",
        tool_name="lookup_order",
    ),
    TraceStep(
        step_index=1,
        action="check_policy",
        observation="refund_policy: 100% refund within 30 days",
        result="eligible",
        tool_name="check_policy",
    ),
    TraceStep(
        step_index=2,
        action="calculate_refund",
        observation="input: price=$150.00, discount_code=SAVE90, discount_applied=90%",
        result="refund=$15.00",
        tool_name="calculate_refund",
    ),
    TraceStep(
        step_index=3,
        action="verify_amount",
        observation="amount=$15.00 above minimum threshold $10.00",
        result="approved",
        tool_name="verify_amount",
    ),
    TraceStep(
        step_index=4,
        action="process_payment",
        observation="payment processed: $15.00 to customer",
        result="completed",
        tool_name="process_payment",
    ),
    TraceStep(
        step_index=5,
        action="send_confirmation",
        observation="email sent: refund_amount=$15.00",
        result="success",
        tool_name="send_confirmation",
    ),
]

incident_trace = AgentTrace(
    trace_id="trace-incident-sess9921",
    agent_name="CustomerServiceAgent",
    task="Process refund for order ORD-9921",
    steps=steps,
)

# ---------------------------------------------------------------------------
# 2. Store and reload
# ---------------------------------------------------------------------------

db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="notarize_forensics_")
os.close(db_fd)

try:
    with TraceStore(db_path) as store:
        store.save_trace(incident_trace)
        reloaded = store.get_trace("trace-incident-sess9921")
finally:
    os.unlink(db_path)

# ---------------------------------------------------------------------------
# 3. Verify hash-chain integrity (confirms trace was not tampered post-hoc)
# ---------------------------------------------------------------------------

verifier = ConsistencyVerifier()
vr = verifier.verify(reloaded)

# ---------------------------------------------------------------------------
# 4. Walk steps chronologically and detect the fault
# ---------------------------------------------------------------------------

print("=" * 70)
print("  TRACE WALKTHROUGH — CustomerServiceAgent session trace-incident-sess9921")
print("=" * 70)

fault_step = None
fault_reason = None
expected_amount = "$150.00"
actual_amount = None

for step in reloaded.steps:
    # Surface any dollar amounts mentioned in this step
    flags = []

    # Detect discount incorrectly applied during refund calculation
    if step.tool_name == "calculate_refund":
        if "discount_code" in step.observation and "discount_applied" in step.observation:
            flags.append("WARNING: discount_code applied during refund calculation")
        if "refund=$15.00" in step.result or "refund=$15.00" in step.observation:
            flags.append("FAULT: refund amount does not match original price $150.00")
            fault_step = step
            actual_amount = "$15.00"
            fault_reason = "discount code SAVE90 incorrectly applied to refund (90% deduction)"

    flag_str = ""
    if flags:
        flag_str = "  <<< " + " | ".join(flags)

    print(
        f"  Step {step.step_index} [{step.tool_name}]"
        f"\n    action      : {step.action}"
        f"\n    observation : {step.observation}"
        f"\n    result      : {step.result}"
        f"{flag_str}"
    )
    print()

# ---------------------------------------------------------------------------
# 5. Forensic report
# ---------------------------------------------------------------------------

integrity_label = "INTACT (verified)" if vr.verdict == "verified" else f"ISSUE ({vr.verdict})"

print("=" * 70)
print("  FORENSIC REPORT")
print("=" * 70)
print(f"Session: {reloaded.trace_id}")
print(f"Agent  : {reloaded.agent_name}")
print(f"Task   : {reloaded.task}")
print(f"Hash chain integrity: {integrity_label}")
print()

if fault_step is not None:
    print(
        f"FORENSIC REPORT — Session {reloaded.trace_id}:\n"
        f"  Step {fault_step.step_index} ({fault_step.tool_name}): "
        f"input had discount_code=SAVE90, output={actual_amount}\n"
        f"  Root cause: discount code incorrectly applied to refund calculation\n"
        f"  Expected output: {expected_amount} | Actual output: {actual_amount}\n"
        f"  Recommendation: patch {fault_step.tool_name} tool to exclude discount codes "
        f"for refund operations"
    )
else:
    print("No fault step identified — manual review required.")

print("=" * 70)
