# Case Study: Rapid Forensics for an Erroneous Autonomous Trading Agent

## Company Profile

**TradeAI** is an algorithmic trading company based in Chicago, IL. With 40 engineers, they build AI agents that execute trades autonomously within defined risk parameters for institutional clients. Their agents operate across equities, options, and futures markets, with per-agent position limits up to $5M. They are registered as an investment adviser and subject to FINRA and SEC recordkeeping requirements for algorithmic trading activity.

## The Problem

On a Thursday morning in Q2 2025, TradeAI's equity arbitrage agent executed a $2.3M position in a mid-cap technology stock at a price 8.2% above the current market bid. The error was caught by a human monitor 4 minutes after execution, and the position was closed at a loss of $187,000 — within risk limits, but material enough to require immediate client notification and internal investigation.

The investigation started with a simple question: "What did the agent see, and what did it calculate, at each step before it placed the order?" The question was impossible to answer.

TradeAI's logging infrastructure captured the agent's final actions (order parameters, execution confirmations) and the raw market data feed. But the agent's internal reasoning — which market data it read, in what order, what calculations it performed, what intermediate conclusions it reached — was not captured. The agent ran inside a LangChain framework with standard logging, which produced a flat timestamp-tagged log of tool calls but no semantic connection between what the agent *observed* and what it *decided* at each step.

Three weeks of investigation by a team of four engineers and a quantitative analyst produced a probable cause: the agent appears to have used a stale price quote from the options chain (delayed by 340ms) as the reference price for the arbitrage calculation. But "appears to have" was the best they could do. They couldn't prove it. The client demanded a root cause confirmation; the compliance team couldn't provide one.

The incident prompted a board-level discussion about AI agent auditability. The conclusion: before deploying any new agent strategy, step-level audit trails were mandatory.

## Solution Architecture

TradeAI integrated notarize into every trading agent session. Each step — market data reads, price calculations, risk checks, order generation — is captured as a `TraceStep`. The complete `AgentTrace` is sealed with a Merkle root and stored before the session ends. When incidents occur, `compare_traces()` immediately surfaces where the incident trace diverged from the expected behavior pattern.

```
┌──────────────────────────────────────────────────────────────────────┐
│                      TradeAI Agent Platform                          │
│                                                                      │
│  Market data tick     ┌────────────────────────────────────────────┐ │
│  arrives          ─► │  Equity Arbitrage Agent                    │ │
│                       │                                            │ │
│                       │  for each reasoning step:                  │ │
│                       │    TraceStep(step_index, action,           │ │
│                       │             observation, result, tool)     │ │
│                       │                                            │ │
│                       │  session ends:                             │ │
│                       │    AgentTrace(steps=[...])                 │ │
│                       │    → Merkle root sealed                    │ │
│                       │    → TraceStore.save()                     │ │
│                       └──────────────────┬─────────────────────────┘ │
│                                          │                            │
│  Incident occurs          AuditSummary   │                            │
│                    ◄─────────────────────┘                            │
│                       summarize(trace)                                │
│                       → which step had wrong data                    │
│                                                                      │
│  Forensic analysis    compare_traces(incident, baseline)             │
│                       → divergence found at step N                   │
│                       → step N observation contains stale price      │
└──────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# tradeai/audit/session_trace.py
import time
from notarize.trace import AgentTrace, TraceStep
from notarize.store import TraceStore
from notarize.verifier import ConsistencyVerifier
from notarize.audit import summarize, AuditSummary
from notarize.timeline import to_csv, to_timeline_json, to_compliance_report

TRACE_DB = "/data/notarize/trading-traces.db"
store = TraceStore(TRACE_DB)


class TradingAgentTracer:
    """Wraps a trading agent session to capture step-level audit traces."""

    def __init__(self, session_id: str, agent_name: str, strategy: str) -> None:
        self.session_id = session_id
        self.agent_name = agent_name
        self.strategy = strategy
        self._steps: list[TraceStep] = []
        self._step_index = 0

    def record_step(
        self,
        action: str,
        observation: str,
        result: str,
        tool_name: str = "",
    ) -> TraceStep:
        """Record a single agent reasoning step."""
        step = TraceStep(
            step_index=self._step_index,
            action=action,
            observation=observation,
            result=result,
            tool_name=tool_name,
            timestamp=time.time(),
        )
        self._steps.append(step)
        self._step_index += 1
        return step

    def seal_and_store(self) -> AgentTrace:
        """Build, verify, and store the complete trace for this session."""
        trace = AgentTrace(
            trace_id=self.session_id,
            agent_name=self.agent_name,
            task=self.strategy,
            steps=self._steps,
        )

        # Verify chain integrity before storage
        verifier = ConsistencyVerifier()
        result = verifier.verify(trace)
        if result.verdict not in ("verified", "consistent"):
            raise RuntimeError(f"Trace integrity check failed: {result.details}")

        store.save(trace)
        return trace


def investigate_incident(
    incident_session_id: str,
    baseline_session_id: str,
) -> str:
    """Compare an incident trace against a baseline to find the divergence.

    Returns a human-readable forensic report.
    """
    incident_trace = store.get(incident_session_id)
    baseline_trace = store.get(baseline_session_id)

    if incident_trace is None:
        return f"No trace found for incident session: {incident_session_id}"
    if baseline_trace is None:
        return f"No trace found for baseline session: {baseline_session_id}"

    # Verify both traces haven't been tampered with
    verifier = ConsistencyVerifier()
    for trace, label in [(incident_trace, "incident"), (baseline_trace, "baseline")]:
        result = verifier.verify(trace)
        if result.verdict not in ("verified", "consistent"):
            return f"INTEGRITY FAILURE on {label} trace — cannot use as forensic evidence."

    # Step-by-step comparison
    incident_summary = summarize(incident_trace)
    baseline_summary = summarize(baseline_trace)

    report_lines = [
        f"# Forensic Investigation: {incident_session_id}",
        "",
        f"## Incident vs. Baseline Comparison",
        f"",
        f"| Metric | Incident | Baseline |",
        f"|--------|----------|----------|",
        f"| Total steps | {incident_summary.total_steps} | {baseline_summary.total_steps} |",
        f"| Duration (ms) | {incident_summary.duration_ms:.0f} | {baseline_summary.duration_ms:.0f} |",
        f"| Tools used | {', '.join(incident_summary.tools_used)} | {', '.join(baseline_summary.tools_used)} |",
        f"| Chain valid | {incident_summary.chain_valid} | {baseline_summary.chain_valid} |",
        "",
        "## Step-by-Step Divergence",
        "",
    ]

    min_steps = min(len(incident_trace.steps), len(baseline_trace.steps))
    for i in range(min_steps):
        inc_step = incident_trace.steps[i]
        base_step = baseline_trace.steps[i]
        if inc_step.observation != base_step.observation or inc_step.result != base_step.result:
            report_lines += [
                f"### Divergence at Step {i} (action: {inc_step.action})",
                "",
                f"**Baseline observation**: `{base_step.observation[:200]}`",
                f"**Incident observation**: `{inc_step.observation[:200]}`",
                f"**Baseline result**: `{base_step.result}`",
                f"**Incident result**: `{inc_step.result}`",
                "",
            ]

    # Export timeline for the incident trace
    timeline_csv = to_csv(incident_trace)
    report_lines += [
        "## Timeline (CSV)",
        "",
        "```csv",
        timeline_csv[:1000],
        "```",
    ]

    return "\n".join(report_lines)
```

When the $2.3M incident was reconstructed with this system and the incident session replayed against a baseline session, `investigate_incident()` identified the divergence in 8 seconds. Step 6 (`action="fetch_reference_price"`, `tool_name="options_chain_reader"`) showed:

- **Baseline observation**: `"ACME Jun 21 call strike 145: bid 2.34 / ask 2.37 (as-of 14:32:07.211)"`
- **Incident observation**: `"ACME Jun 21 call strike 145: bid 2.34 / ask 2.37 (as-of 14:31:51.420)"`

A 15-second-stale quote. The root cause was identified in 2 hours rather than 3 weeks.

## Results

- **Incident root cause identification: 3 weeks → 2 hours** — the forensic report from `investigate_incident()` gave compliance and engineering teams a specific step, a specific observation, and a specific tool call to investigate
- **90% of agent incidents now resolved same-day** by the compliance team without requiring engineering escalation — `AuditSummary` gives them enough context to triage independently
- **Zero unsolved agent incidents in 6 months** since deployment — previously, 2-3 incidents per quarter had no determined root cause and were closed as "indeterminate"
- **FINRA recordkeeping requirement satisfied**: `to_compliance_report(trace, standard="SOC2")` generates the required audit trail format; the CSV export (`to_csv()`) satisfies the machine-readable recordkeeping requirement
- **Trace overhead**: each `TraceStep` record adds approximately 0.3ms to step latency — immaterial at trading agent timescales (steps run in 50-200ms)

## Key Takeaways

- Step-level observation capture is the minimum viable forensic unit. Tool call logs tell you *what* the agent called; `TraceStep.observation` tells you *what the agent saw* — the crucial difference for root cause analysis.
- Tamper evidence determines whether a trace is forensically useful. A log that could be modified post-incident is not evidence. The Merkle-sealed `AgentTrace` gives compliance teams the same confidence in the trace as in a timestamped exchange record.
- `compare_traces()` is faster than every other investigation method. Rather than manually reading two traces step by step, the automated comparison surfaces the exact divergent step in seconds.
- Incident response and compliance reporting use the same artifact. The `AgentTrace` serves both the engineering post-mortem (step-level divergence analysis) and the regulatory submission (HIPAA/SOC2 compliance report). One capture infrastructure, two use cases.
- `AuditSummary.risk_flags` operationalizes incident triage. Flags like `"many_steps"` and `"long_duration"` give compliance teams a structured first-pass filter without requiring them to read raw traces.

## Try It Yourself

```bash
# Install notarize
pip install notarize

# Simulate two trading agent traces and compare them
python -c "
import time
from notarize.trace import AgentTrace, TraceStep
from notarize.store import TraceStore

steps_baseline = [
    TraceStep(0, 'fetch_market_data', 'SPY bid 502.14 ask 502.16 (now)', 'success', 'market_feed', time.time()),
    TraceStep(1, 'fetch_reference_price', 'options chain: 145c bid 2.37 (now)', 'success', 'options_reader', time.time()),
    TraceStep(2, 'calculate_arb', 'spread = 0.12, above threshold', 'execute', '', time.time()),
]
steps_incident = [
    TraceStep(0, 'fetch_market_data', 'SPY bid 502.14 ask 502.16 (now)', 'success', 'market_feed', time.time()),
    TraceStep(1, 'fetch_reference_price', 'options chain: 145c bid 2.34 (15s stale)', 'success', 'options_reader', time.time()),
    TraceStep(2, 'calculate_arb', 'spread = 0.15, above threshold', 'execute', '', time.time()),
]
store = TraceStore('/tmp/trading-traces.db')
store.save(AgentTrace('baseline-001', 'arb-agent', 'equity-arb', steps_baseline))
store.save(AgentTrace('incident-001', 'arb-agent', 'equity-arb', steps_incident))
print('Traces stored. Run: notarize log --db /tmp/trading-traces.db')
"

notarize log --db /tmp/trading-traces.db
notarize verify --db /tmp/trading-traces.db incident-001
```
