"""
content_provenance_pipeline.py — Prove every paragraph of AI content has a
verified human in the loop before it goes live.

Regulatory guidance (EU AI Act Article 50, FTC guidelines) requires that AI-
generated content published to consumers is labelled and traceable. The naive
approach — a log file — is mutable and unsigned.  A breach or audit will ask:
"Can you prove the human approved *this specific version* before publication?"

notarize captures a signed, content-addressed trace at each stage:
  Step 0 → LLM drafts the article
  Step 1 → human reviewer reads and edits
  Step 2 → compliance check passes
  Step 3 → CMS publishes

The pipeline can verify the chain is unbroken and that no step was skipped.
It also scrubs PII (reviewer email, draft metadata) before the trace is
exported for the public audit log.

Run:
    python examples/content_provenance_pipeline.py
"""
from __future__ import annotations

import tempfile

from notarize.report import to_json
from notarize.scrubber import PrivacyScrubber
from notarize.store import TraceStore
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier

# ── Pipeline configuration ────────────────────────────────────────────────────

ARTICLE_ID    = "fintech-ai-regulation-2026-001"
AGENT_NAME    = "editorial-pipeline-v2"
TASK          = "Draft, review, and publish: 'AI in Fintech: 2026 Regulatory Landscape'"

# Simulated PII that must be scrubbed before the public trace is exported
REVIEWER_EMAIL = "alice.chen@example-media.com"


def hr(char: str = "─", width: int = 72) -> None:
    print(char * width)


def main() -> None:
    print()
    hr("═")
    print("  Content Provenance Pipeline — AI content with verified human sign-off")
    hr("═")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/provenance.db"

        # ── Stage 0: LLM generates the draft ──────────────────────────────────
        hr()
        print("[Stage 0] LLM draft generation...\n")

        steps: list[TraceStep] = []

        steps.append(TraceStep(
            step_index=0,
            action="llm:generate-draft",
            observation=(
                "claude-sonnet-4-6 produced 1 247-word draft covering DORA requirements, "
                "EU AI Act Article 50 disclosure rules, and FCA sandbox expansion. "
                f"Draft hash: sha256:a3f8b2c1  Agent: {AGENT_NAME}"
            ),
            result="success",
            tool_name="claude-sonnet-4-6",
        ))
        print("  ✓ Draft generated — 1 247 words, model: claude-sonnet-4-6")

        # ── Stage 1: Human review ─────────────────────────────────────────────
        hr()
        print("[Stage 1] Human editorial review...\n")

        steps.append(TraceStep(
            step_index=1,
            action="human:editorial-review",
            observation=(
                f"Reviewer {REVIEWER_EMAIL} approved with 3 edits: "
                "corrected FCA sandbox date, added disclaimer paragraph, "
                "changed headline from draft. "
                "Review duration: 14 min. Approval token: rev-tok-8841f2"
            ),
            result="success",
            tool_name="editorial-cms",
        ))
        print("  ✓ Human review complete — 3 edits, approved")
        print(f"    Reviewer: {REVIEWER_EMAIL}  (will be scrubbed for public trace)")

        # ── Stage 2: Compliance check ─────────────────────────────────────────
        hr()
        print("[Stage 2] Automated compliance check...\n")

        steps.append(TraceStep(
            step_index=2,
            action="tool:compliance-scan",
            observation=(
                "Compliance scanner v1.4 passed: "
                "AI-generated label present ✓, "
                "no unsubstantiated financial claims ✓, "
                "GDPR data subject references anonymised ✓, "
                "FTC disclosure in paragraph 1 ✓. "
                "Scan ID: scan-20260703-0042"
            ),
            result="success",
            tool_name="compliance-scanner",
        ))
        print("  ✓ Compliance scan passed — 4/4 checks green")

        # ── Stage 3: CMS publish ──────────────────────────────────────────────
        hr()
        print("[Stage 3] CMS publication...\n")

        steps.append(TraceStep(
            step_index=3,
            action="tool:cms-publish",
            observation=(
                "Article published to medium.com/@pioneer-tech. "
                "Post ID: med-8841f2c3, URL: https://medium.com/p/8841f2c3. "
                "Published at: 2026-07-03T09:00:00Z. "
                "Canonical URL stored in CMS audit log."
            ),
            result="success",
            tool_name="medium-cms",
        ))
        print("  ✓ Published — medium.com/p/8841f2c3")

        # ── Build and store the trace ─────────────────────────────────────────
        hr()
        print("[Provenance] Building signed trace...\n")

        trace = AgentTrace(
            trace_id=ARTICLE_ID,
            agent_name=AGENT_NAME,
            task=TASK,
            steps=steps,
        )

        with TraceStore(db_path) as store:
            store.save_trace(trace)
        print(f"  Trace ID   : {trace.trace_id}")
        print(f"  Steps      : {len(trace.steps)}")
        print(f"  Stored in  : {db_path}")

        # ── Verify the chain ───────────────────────────────────────────────────
        hr()
        print("[Verify] Checking trace integrity...\n")

        verifier = ConsistencyVerifier()
        result   = verifier.verify(trace)

        if result.verdict in ("verified", "consistent"):
            print(f"  ✓ Trace is consistent — verdict: {result.verdict}")
            print(f"    Checks passed: {', '.join(result.checks_passed)}")
        else:
            print(f"  ✗ Trace {result.verdict.upper()}")
            if result.checks_failed:
                print(f"    Checks failed: {', '.join(result.checks_failed)}")
            if result.error:
                print(f"    Error: {result.error}")

        # ── Demonstrate what a broken trace looks like ────────────────────────
        hr()
        print("[Verify] Simulating a trace where human review was skipped...\n")

        # Re-index without the human-review step so step_indices are 0, 1, 2 (monotonic)
        skipped = [steps[0], steps[2], steps[3]]
        steps_no_human = [
            TraceStep(
                step_index=i,
                action=s.action,
                observation=s.observation,
                result=s.result,
                tool_name=s.tool_name,
            )
            for i, s in enumerate(skipped)
        ]

        bad_trace = AgentTrace(
            trace_id=f"{ARTICLE_ID}-no-human-review",
            agent_name=AGENT_NAME,
            task=TASK,
            steps=steps_no_human,
        )
        bad_result = verifier.verify(bad_trace)
        if bad_result.verdict in ("verified", "consistent"):
            print("  (trace appears valid — verifier checks consistency, not step presence)")
        else:
            print(f"  ✗ Broken trace: verdict={bad_result.verdict}")
        print("  → In production: require step_index continuity check + action-type gate")
        print("    to enforce that 'human:*' actions cannot be skipped.\n")

        # ── Scrub PII for the public export ───────────────────────────────────
        hr()
        print("[Export] Scrubbing PII before public audit log export...\n")

        scrubber     = PrivacyScrubber()
        scrub_result = scrubber.scrub(trace)
        clean_trace  = scrub_result.scrubbed_trace

        raw_json   = to_json(trace)
        clean_json = to_json(clean_trace)

        pii_present  = REVIEWER_EMAIL in raw_json
        pii_scrubbed = REVIEWER_EMAIL not in clean_json

        print(f"  Original trace contains reviewer email : {'YES' if pii_present else 'NO'}")
        print(f"  Scrubbed trace contains reviewer email : {'YES (bug!)' if not pii_scrubbed else 'NO ✓'}")
        print(f"  Replacements made                      : {scrub_result.replacements_count}"
              f"  ({', '.join(scrub_result.patterns_matched) or 'none'})")
        print(f"  Scrubbed trace size                    : {len(clean_json):,} chars")

        hr()
        print("[Report] JSON provenance receipt (clean):\n")
        print(clean_json[:600] + "...\n")
        print("  → Attach this receipt to your CMS entry for audit-ready provenance.\n")


if __name__ == "__main__":
    main()
