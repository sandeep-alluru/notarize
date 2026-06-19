"""multi_agent_provenance.py

Multi-agent pipeline provenance demo: DataAgent -> AnalysisAgent -> ReportAgent.

Each agent produces its own AgentTrace. The downstream agent's task field
records its parent's trace_id so the chain of custody can be reconstructed.
All three traces are stored in a single TraceStore, then verified and walked
backwards from ReportAgent to DataAgent to answer: "which raw data led to
this conclusion?"
"""

import os
import tempfile

from notarize.store import TraceStore
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier

# ---------------------------------------------------------------------------
# 1. DataAgent — fetches raw datasets
# ---------------------------------------------------------------------------

data_steps = [
    TraceStep(
        step_index=0,
        action="connect_source: source=sales_db host=db.internal.corp",
        observation="Connected to sales_db. Tables available: orders, customers, products.",
        result="connected",
        tool_name="connect_source",
    ),
    TraceStep(
        step_index=1,
        action="fetch_dataset: table=orders date_range=2025-Q4",
        observation="Fetched 14,382 order rows. Columns: order_id, product_id, amount, ts.",
        result="14382_rows",
        tool_name="fetch_dataset",
    ),
    TraceStep(
        step_index=2,
        action="fetch_dataset: table=products",
        observation="Fetched 312 product rows. Columns: product_id, name, category, unit_cost.",
        result="312_rows",
        tool_name="fetch_dataset",
    ),
    TraceStep(
        step_index=3,
        action="export_dataset: format=parquet destination=s3://pipeline/raw/2025-Q4/",
        observation="Exported 2 parquet files: orders.parquet (4.1 MB), products.parquet (88 KB).",
        result="export_complete",
        tool_name="export_dataset",
    ),
]

data_trace = AgentTrace(
    trace_id="trace-data-001",
    agent_name="DataAgent",
    task="Fetch raw sales and product datasets for Q4 2025",
    steps=data_steps,
)

# ---------------------------------------------------------------------------
# 2. AnalysisAgent — processes the raw data produced by DataAgent
# ---------------------------------------------------------------------------

analysis_steps = [
    TraceStep(
        step_index=0,
        action="load_data: source=s3://pipeline/raw/2025-Q4/",
        observation="Loaded orders.parquet (14,382 rows) and products.parquet (312 rows).",
        result="loaded",
        tool_name="load_data",
    ),
    TraceStep(
        step_index=1,
        action="join_datasets: left=orders right=products on=product_id",
        observation="Join complete. Result: 14,382 rows with 7 columns.",
        result="14382_rows_joined",
        tool_name="join_datasets",
    ),
    TraceStep(
        step_index=2,
        action="compute_metrics: group_by=category metrics=total_revenue,unit_count",
        observation="Top category: Electronics $2.1M (3,241 units). Bottom: Stationery $18K (402 units).",
        result="metrics_computed",
        tool_name="compute_metrics",
    ),
    TraceStep(
        step_index=3,
        action="export_analysis: destination=s3://pipeline/analysis/2025-Q4/metrics.json",
        observation="Metrics JSON exported. 8 category rows, totals validated.",
        result="export_complete",
        tool_name="export_analysis",
    ),
]

analysis_trace = AgentTrace(
    trace_id="trace-analysis-001",
    agent_name="AnalysisAgent",
    task="Compute Q4 2025 sales metrics by category | parent_trace=trace-data-001",
    steps=analysis_steps,
)

# ---------------------------------------------------------------------------
# 3. ReportAgent — generates the executive report from analysis results
# ---------------------------------------------------------------------------

report_steps = [
    TraceStep(
        step_index=0,
        action="load_metrics: source=s3://pipeline/analysis/2025-Q4/metrics.json",
        observation="Loaded 8 category metrics. Total Q4 revenue: $4.7M across 14,382 orders.",
        result="loaded",
        tool_name="load_metrics",
    ),
    TraceStep(
        step_index=1,
        action="generate_narrative: template=executive_summary",
        observation="Narrative drafted. Key insight: Electronics drove 44.7% of Q4 revenue.",
        result="narrative_ready",
        tool_name="generate_narrative",
    ),
    TraceStep(
        step_index=2,
        action="render_report: format=pdf destination=s3://pipeline/reports/Q4-2025-exec.pdf",
        observation="PDF rendered. 12 pages. Charts: revenue_by_category, monthly_trend, top_products.",
        result="report_published",
        tool_name="render_report",
    ),
]

report_trace = AgentTrace(
    trace_id="trace-report-001",
    agent_name="ReportAgent",
    task="Generate Q4 2025 executive sales report | parent_trace=trace-analysis-001",
    steps=report_steps,
)

# ---------------------------------------------------------------------------
# 4. Store all 3 traces in a single TraceStore
# ---------------------------------------------------------------------------

db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="notarize_pipeline_")
os.close(db_fd)

verifier = ConsistencyVerifier()

try:
    with TraceStore(db_path) as store:
        for t in (data_trace, analysis_trace, report_trace):
            store.save_trace(t)

        # ---------------------------------------------------------------------------
        # 5. Verify each trace and reconstruct the forward chain
        # ---------------------------------------------------------------------------

        all_traces = store.list_traces()  # ordered by created_at

        print("=" * 70)
        print("  MULTI-AGENT PIPELINE — CHAIN OF CUSTODY")
        print("=" * 70)

        results = {}
        for t in all_traces:
            vr = verifier.verify(t)
            results[t.trace_id] = vr
            status = "OK" if vr.verdict == "verified" else vr.verdict.upper()
            print(f"  [{status}] {t.agent_name} ({t.trace_id}) — {len(t.steps)} steps")

        # ---------------------------------------------------------------------------
        # 6. Walk backwards from ReportAgent to DataAgent
        # ---------------------------------------------------------------------------

        print()
        print("  BACKWARD PROVENANCE WALK")
        print("  Question: 'Which raw data led to the Q4 executive report?'")
        print()

        def extract_parent_trace_id(task: str) -> str | None:
            """Pull parent_trace=<id> from a task string, if present."""
            for token in task.split("|"):
                token = token.strip()
                if token.startswith("parent_trace="):
                    return token.split("=", 1)[1].strip()
            return None

        # Start from report
        current = store.get_trace("trace-report-001")
        chain = [current]

        while True:
            parent_id = extract_parent_trace_id(current.task)
            if parent_id is None:
                break
            parent = store.get_trace(parent_id)
            if parent is None:
                break
            chain.append(parent)
            current = parent

        chain.reverse()  # oldest first: Data -> Analysis -> Report

        for i, t in enumerate(chain):
            arrow = "  " if i == 0 else "  <- "
            print(f"{arrow}{t.agent_name} ({t.trace_id})")
            print(f"       task : {t.task}")
            print(f"       steps: {len(t.steps)}")
            if t.steps:
                first = t.steps[0]
                print(f"       first action: {first.action}")
            print()

finally:
    os.unlink(db_path)

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------

all_verified = all(r.verdict == "verified" for r in results.values())
chain_status = "INTACT" if all_verified else "BROKEN"

print("=" * 70)
print(
    f"DataAgent -> AnalysisAgent -> ReportAgent: "
    f"all {len(results)} traces verified, "
    f"chain of custody {chain_status}"
)
print("=" * 70)
