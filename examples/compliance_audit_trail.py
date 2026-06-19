"""compliance_audit_trail.py

Healthcare AI Agent — HIPAA / SOC2 compliance demonstration.

A HealthcareAuditAgent reviews three patient records and flags anomalies.
The trace is scrubbed of PII (phone, email, SSN), stored in SQLite, reloaded,
and verified for hash-chain integrity — producing a SOC2-ready audit report.
"""

import tempfile
import os

from notarize.trace import AgentTrace, TraceStep
from notarize.store import TraceStore
from notarize.verifier import ConsistencyVerifier
from notarize.scrubber import PrivacyScrubber


# ---------------------------------------------------------------------------
# 1. Build the raw (pre-scrub) trace
# ---------------------------------------------------------------------------

steps = [
    # --- Patient P001 ---
    TraceStep(
        step_index=0,
        action="read_record: patient_id=P001 contact=555-867-5309 email=john.doe@hospital.com",
        observation="Record loaded: DOB field present, SSN=123-45-6789",
        result="success",
        tool_name="read_record",
    ),
    TraceStep(
        step_index=1,
        action="analyze_symptoms: patient_id=P001",
        observation="Symptoms: hypertension, fatigue. Last visit: 2025-11-03. No critical flags.",
        result="no_anomaly",
        tool_name="analyze_symptoms",
    ),
    TraceStep(
        step_index=2,
        action="generate_recommendation: patient_id=P001",
        observation="Recommended follow-up in 90 days. Medication: amlodipine 5mg.",
        result="recommendation_generated",
        tool_name="generate_recommendation",
    ),
    # --- Patient P002 ---
    TraceStep(
        step_index=3,
        action="read_record: patient_id=P002 contact=555-234-5678 email=jane.smith@clinic.org",
        observation="Record loaded: DOB present, SSN=987-65-4321, allergy_flag=TRUE",
        result="success",
        tool_name="read_record",
    ),
    TraceStep(
        step_index=4,
        action="analyze_symptoms: patient_id=P002",
        observation="Symptoms: chest pain, shortness of breath. CRITICAL anomaly detected: possible cardiac event.",
        result="anomaly_detected",
        tool_name="analyze_symptoms",
    ),
    TraceStep(
        step_index=5,
        action="generate_recommendation: patient_id=P002",
        observation="Escalated to cardiologist. Emergency referral logged. Contact: 555-999-0001",
        result="escalation_issued",
        tool_name="generate_recommendation",
    ),
    # --- Patient P003 ---
    TraceStep(
        step_index=6,
        action="read_record: patient_id=P003 contact=555-111-2233 email=robert.jones@healthnet.com",
        observation="Record loaded: DOB present, SSN=321-54-9876",
        result="success",
        tool_name="read_record",
    ),
    TraceStep(
        step_index=7,
        action="analyze_symptoms: patient_id=P003",
        observation="Symptoms: mild fever, cough. Duration 5 days. Within normal parameters.",
        result="no_anomaly",
        tool_name="analyze_symptoms",
    ),
    TraceStep(
        step_index=8,
        action="generate_recommendation: patient_id=P003",
        observation="Recommended rest, fluids. Follow-up only if symptoms persist beyond 7 days.",
        result="recommendation_generated",
        tool_name="generate_recommendation",
    ),
]

raw_trace = AgentTrace(
    trace_id="trace-hipaa-001",
    agent_name="HealthcareAuditAgent",
    task="Review patient records and flag anomalies",
    steps=steps,
)

# ---------------------------------------------------------------------------
# 2. Scrub PII from the trace
# ---------------------------------------------------------------------------

scrubber = PrivacyScrubber()
scrub_result = scrubber.scrub(raw_trace)
scrubbed_trace = scrub_result.scrubbed_trace

# ---------------------------------------------------------------------------
# 3. Side-by-side before/after display
# ---------------------------------------------------------------------------

print("=" * 70)
print("  PII SCRUBBING — BEFORE / AFTER")
print("=" * 70)

raw_steps = raw_trace.steps
clean_steps = scrubbed_trace.steps

for i in range(len(raw_steps)):
    raw_s = raw_steps[i]
    clean_s = clean_steps[i]
    changed = (
        raw_s.action != clean_s.action
        or raw_s.observation != clean_s.observation
        or raw_s.result != clean_s.result
    )
    if changed:
        print(f"\nStep {i} ({raw_s.tool_name}):")
        if raw_s.action != clean_s.action:
            print(f"  action  BEFORE: {raw_s.action}")
            print(f"          AFTER : {clean_s.action}")
        if raw_s.observation != clean_s.observation:
            print(f"  observe BEFORE: {raw_s.observation}")
            print(f"          AFTER : {clean_s.observation}")
        if raw_s.result != clean_s.result:
            print(f"  result  BEFORE: {raw_s.result}")
            print(f"          AFTER : {clean_s.result}")

print(f"\nPatterns matched : {scrub_result.patterns_matched}")
print(f"Total fields scrubbed: {scrub_result.replacements_count}")

# ---------------------------------------------------------------------------
# 4. Store the SCRUBBED trace, reload, and verify
# ---------------------------------------------------------------------------

db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="notarize_hipaa_")
os.close(db_fd)

try:
    with TraceStore(db_path) as store:
        store.save_trace(scrubbed_trace)

        # Reload from store
        reloaded = store.get_trace("trace-hipaa-001")

    # Verify integrity
    verifier = ConsistencyVerifier()
    result = verifier.verify(reloaded)

finally:
    os.unlink(db_path)

# ---------------------------------------------------------------------------
# 5. Audit report
# ---------------------------------------------------------------------------

verdict_label = "VERIFIED" if result.verdict == "verified" else result.verdict.upper()
compliance_status = "SOC2-READY" if result.verdict == "verified" else "REVIEW-REQUIRED"

print()
print("=" * 70)
print("  AUDIT REPORT")
print("=" * 70)
print(
    f"Audit Trail for {raw_trace.trace_id}: "
    f"{len(raw_trace.steps)} steps recorded, "
    f"PII scrubbed ({scrub_result.replacements_count} fields), "
    f"hash chain: {verdict_label} ✓, "
    f"compliance: {compliance_status}"
)
print(f"  Agent           : {raw_trace.agent_name}")
print(f"  Task            : {raw_trace.task}")
print(f"  Checks passed   : {result.checks_passed}")
print(f"  Checks failed   : {result.checks_failed}")
print(f"  Merkle root     : {scrubbed_trace.merkle_root}")
print(f"  Anomalies found : 1 (Step 4 — Patient P002, cardiac event)")
print("=" * 70)
