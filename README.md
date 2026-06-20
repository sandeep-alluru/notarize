# notarize

**Canonical trace format and verifier for agent execution attestation.**

![notarize](assets/hero.png)

[![CI](https://github.com/sandeep-alluru/notarize/actions/workflows/ci.yml/badge.svg)](https://github.com/sandeep-alluru/notarize/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/notarize.svg)](https://pypi.org/project/notarize/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/notarize.svg)](https://pypi.org/project/notarize/)
[![Downloads](https://img.shields.io/pypi/dm/notarize.svg)](https://pypi.org/project/notarize/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![codecov](https://codecov.io/gh/sandeep-alluru/notarize/branch/main/graph/badge.svg)](https://codecov.io/gh/sandeep-alluru/notarize)
[![Typed](https://img.shields.io/badge/types-mypy-blue)](https://mypy-lang.org/)

[Quick Start](#quick-start) · [How It Works](#how-it-works) · [CLI Reference](#cli-reference) · [GitHub Action](#github-action) · [vs. Alternatives](#vs-alternatives) · [Contributing](CONTRIBUTING.md)

---

## Why

AI agents produce execution traces. Those traces are the primary audit artifact for regulatory compliance, forensic analysis, and debugging. The problem: no canonical format, no tamper detection, no PII scrubbing pipeline.

When an agent's trace is submitted for an EU AI Act audit, how do you know it hasn't been modified? How do you ensure personal data was redacted before storage? How do you verify the step sequence is internally consistent?

notarize solves this by treating agent traces like signed commits: every step is content-addressed, steps are hash-chained, and a Merkle root seals the whole trace. Tamper any step and the verifier catches it.

```
notarize verify trace.json   # exits 1 if tampered
notarize scrub trace.json    # removes PII before storage
```

---

## How It Works

```mermaid
flowchart LR
    A[Agent records TraceStep\naction · observation · result] --> B[SHA-256 ID\ncontent-addressed]
    B --> C[Hash Chain\nparent_id links]
    C --> D[Merkle Root\nover all step IDs]
    D --> E[AgentTrace\ntrace_id · agent · task]
    E --> F{ConsistencyVerifier}
    F --> G[VerificationResult\nverified / tampered / invalid]
    F --> H[PrivacyScrubber\nremoves PII]
    H --> I[ScrubResult\nclean trace]
```

**Core primitives:**

- **TraceStep** — a single agent action with SHA-256[:16] ID derived from step_index, action, observation, and result.
- **AgentTrace** — a hash-chained sequence of TraceSteps with a Merkle root sealing the whole trace.
- **ConsistencyVerifier** — checks hash chain integrity, Merkle root, step indices, and trace ID.
- **PrivacyScrubber** — structure-preserving PII redaction (email, phone, credit card, SSN, IP).

---

## Features

| Feature | Details |
|---------|---------|
| Content-addressed steps | Same step content always produces the same ID |
| Hash chain | Each step's parent_id links to the previous step's ID |
| Merkle root | Seals the full trace — tamper any step and it breaks |
| 5 verification checks | Chain integrity, Merkle root, monotonic indices, no duplicates, trace ID |
| PII scrubbing | Removes email, phone, credit card, SSN, IP addresses |
| SQLite store | Local-first, no server required |
| CLI | `verify`, `scrub`, `log`, `status` subcommands |
| FastAPI REST server | `/verify`, `/scrub`, `/traces`, `/trace/{id}` endpoints |
| MCP server | Model Context Protocol integration for Claude and other agents |
| 165+ tests | Comprehensive test suite, 85%+ branch coverage |

---

## Quick Start

```bash
pip install notarize
```

> **Debian/Ubuntu users:** if you see `ensurepip is not available` when creating a virtualenv, first run `sudo apt install python3-venv` and then re-create the virtualenv.

```python
from notarize import AgentTrace, TraceStep, ConsistencyVerifier, PrivacyScrubber

# Build a trace
steps = [
    TraceStep(0, "tool_call:search", "Found 5 results", "success", tool_name="search"),
    TraceStep(1, "tool_call:read",   "Read file content", "success", tool_name="read"),
    TraceStep(2, "tool_call:write",  "Wrote output", "success", tool_name="write"),
]
trace = AgentTrace(
    trace_id="audit-2024-001",
    agent_name="compliance-agent",
    task="Review contract documents",
    steps=steps,
)

# Verify internal consistency
verifier = ConsistencyVerifier()
result = verifier.verify(trace)
print(result.verdict)  # "verified"

# Scrub PII before storing
scrubber = PrivacyScrubber()
scrub = scrubber.scrub(trace)
print(scrub.replacements_count)  # 0 (no PII in this trace)
```

---

## CLI Reference

```bash
notarize [--db PATH] COMMAND [OPTIONS]
```

| Command | Description | Key options |
|---------|-------------|-------------|
| `verify FILE` | Verify a JSON trace file for consistency | `--format {rich,json}`, `--save` |
| `scrub FILE` | Scrub PII from a trace file | `-o OUTPUT` |
| `log` | List all stored traces | — |
| `status` | Show store info (trace/result counts) | — |
| `audit FILE` | Print a human-readable audit summary (step count, tool breakdown, risk flags) | — |

**Global options:**

| Option | Default | Env var |
|--------|---------|---------|
| `--db PATH` | `.notarize/traces.db` | `NOTARIZE_DB` |

**Examples:**

```bash
# Verify a trace
notarize verify trace.json

# Verify and save to the database
notarize verify trace.json --save

# Scrub PII and output to stdout
notarize scrub trace.json

# Scrub PII and save to file
notarize scrub trace.json -o scrubbed.json

# List stored traces
notarize log

# Show store statistics
notarize status
```

---

## Advanced API

These functions and classes are part of the public API (exported from `notarize`) but are not shown in the Quick Start example.

### Comparing two traces

```python
from notarize import compare_traces, TraceComparison

comparison: TraceComparison = compare_traces(trace_a, trace_b)
print(comparison.added_steps)    # steps in trace_b but not trace_a
print(comparison.removed_steps)  # steps in trace_a but not trace_b
print(comparison.changed_steps)  # StepComparison objects for differing steps
print(comparison.is_equivalent)  # True if no structural differences
```

### Audit summaries

```python
from notarize import summarize, AuditSummary

summary: AuditSummary = summarize(trace)
print(summary.step_count)       # total number of steps
print(summary.tool_breakdown)   # dict[tool_name, call_count]
print(summary.risk_flags)       # list of flagged issues
```

### Export formats

```python
from notarize import to_timeline_json, to_csv, to_compliance_report

# JSON timeline suitable for visualisation tools
json_str: str = to_timeline_json(trace)

# CSV export for spreadsheet analysis
csv_str: str = to_csv(trace)

# Markdown compliance report (EU AI Act / SOC 2 style)
md_str: str = to_compliance_report(trace)
```

---

## GitHub Action

Add notarize verification to your CI pipeline:

```yaml
# .github/workflows/notarize.yml
name: Verify agent traces
on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: sandeep-alluru/notarize@main
        with:
          trace-file: traces/latest.json
          fail-on-tampered: "true"
```

The action installs notarize and runs `notarize verify` on the specified trace file. See [docs/github-action.md](docs/github-action.md) for full documentation.

---

## vs. Alternatives

| | notarize | LangSmith | Arize Phoenix | Weave (W&B) | OpenTelemetry |
|---|---|---|---|---|---|
| **Hash-chained steps** | Yes — tamper-evident | No | No | No | No |
| **Merkle root attestation** | Yes | No | No | No | No |
| **EU AI Act / audit focus** | Yes | No | No | No | No |
| **PII scrubbing built-in** | Yes | No | Partial | No | No |
| **Offline / local-first** | Yes — single SQLite | No (cloud) | Partial | No (cloud) | Partial |
| **Content-addressed steps** | Yes | No | No | No | No |
| **Open source** | MIT | Closed | MIT | Apache 2.0 | Apache 2.0 |
| **Primary purpose** | Trace attestation | Observability | ML monitoring | Experiment tracking | Distributed tracing |

notarize is purpose-built for compliance audit use cases where tamper-evidence and PII handling are first-class requirements.

---

## Claude / MCP integration

notarize ships a Model Context Protocol server that lets Claude and other MCP-compatible agents verify and scrub traces directly:

```bash
# Start the MCP server
notarize-mcp

# In your Claude Code project's .claude/settings.json:
{
  "mcpServers": {
    "notarize": {
      "command": "notarize-mcp"
    }
  }
}
```

Once connected, Claude can call `verify_trace`, `scrub_trace`, and `list_traces` as tools. See [docs/mcp.md](docs/mcp.md) for the full tool schema.

---

## OpenAI integration

notarize exposes a FastAPI REST server compatible with OpenAI's function-calling format. The tool definitions are in [`tools/openai-tools.json`](tools/openai-tools.json) and the full API spec is in [`openapi.yaml`](openapi.yaml).

```bash
# Start the REST server
uvicorn notarize.api:app --reload

# Pass to Codex CLI or any OpenAI-compatible agent
codex --tools tools/openai-tools.json "Verify the latest agent trace"
```

Endpoints: `GET /health`, `POST /verify`, `POST /scrub`, `GET /traces`, `GET /trace/{id}`. See [docs/openai.md](docs/openai.md) for details.

---

## Case Studies

See how teams are using notarize in production:

- [HIPAA-Compliant Audit Trails for Clinical AI Agents](docs/case-studies/healthcare-hipaa-compliance.md)
- [Rapid Forensics for an Erroneous Autonomous Trading Agent](docs/case-studies/fintech-agent-forensics.md)

---

## Repository structure

```
notarize/
├── src/
│   └── notarize/
│       ├── trace.py          # TraceStep, AgentTrace dataclasses + hash chain
│       ├── verifier.py       # ConsistencyVerifier, VerificationResult
│       ├── scrubber.py       # PrivacyScrubber, ScrubResult + PII patterns
│       ├── store.py          # SQLite-backed TraceStore
│       ├── report.py         # print_result(), print_trace(), to_json(), to_markdown()
│       ├── cli.py            # Click CLI (verify, scrub, log, status)
│       ├── api.py            # FastAPI REST server
│       └── mcp_server.py     # MCP server
├── tests/
│   ├── test_trace.py         # TraceStep, AgentTrace, hash chain, merkle root
│   ├── test_verifier.py      # ConsistencyVerifier with valid/tampered/invalid traces
│   ├── test_scrubber.py      # PII patterns, replacement, ScrubResult
│   ├── test_store.py         # TraceStore save/get/list
│   ├── test_report.py        # Formatters
│   ├── test_cli_runner.py    # Click CliRunner tests
│   └── test_api.py           # FastAPI TestClient tests
├── examples/
│   └── demo.py               # Standalone demo script
├── docs/                     # MkDocs documentation
├── tools/
│   └── openai-tools.json     # OpenAI function-calling tool definitions
├── assets/
│   ├── hero.png              # README hero image
│   └── logo.png              # Project logo
├── action.yml                # GitHub Action
├── openapi.yaml              # OpenAPI 3.1 spec
├── pyproject.toml            # Package metadata + dependencies
└── CONTRIBUTING.md           # Contribution guide
```

---

## Real-World Scenario

**Regulatory: Proving Agent Decisions Weren't Tampered With (EU AI Act)**

A compliance auditor requests trace records for 3 loan decisions. Before submission, a bad actor modifies step 1 to hide a biased "approved" decision. notarize's Merkle-chained trace catches the tamper immediately:

```python
import json
from notarize import AgentTrace, TraceStep, ConsistencyVerifier

# --- 1. Build the original loan-decision trace ---
steps = [
    TraceStep(0, "risk_model:score",    "Credit score: 720, DTI: 0.28",  "approved", tool_name="risk_model"),
    TraceStep(1, "policy_check:verify", "All policy gates passed",        "approved", tool_name="policy_check"),
    TraceStep(2, "decision:record",     "Decision logged to ledger",      "approved", tool_name="decision"),
]
trace = AgentTrace(
    trace_id="loan-audit-2025-EU-0042",
    agent_name="loan-decision-agent",
    task="Evaluate loan application #LN-98231 for EUR 45,000",
    steps=steps,
)

# --- 2. Serialize to JSON (as would be stored/submitted for audit) ---
trace_json = json.dumps(trace.to_dict(), indent=2)
print("Original trace serialized. Merkle root:", trace.merkle_root)

# --- 3. Bad actor tampers with step 1 — changes "approved" to "denied"
#         to make it look like the agent correctly rejected the application ---
tampered_dict = json.loads(trace_json)
tampered_dict["steps"][1]["result"] = "denied"   # cover up the biased approval
print("\nTampered: step 1 result changed from 'approved' -> 'denied'")

# --- 4. Rebuild an AgentTrace from the tampered dict ---
tampered_trace = AgentTrace.from_dict(tampered_dict)

# --- 5. Run ConsistencyVerifier against the tampered trace ---
result = ConsistencyVerifier().verify(tampered_trace)

# --- 6. Verification fails — tamper is caught ---
print("\nVerdict      :", result.verdict)           # "tampered"
print("Checks failed:", result.checks_failed)
# Example output:
#   Verdict      : tampered
#   Checks failed: ['hash_chain_integrity', 'tamper_detected', 'merkle_root_valid', 'trace_id_valid']

assert result.verdict == "tampered", "Expected tamper to be caught!"
assert "tamper_detected" in result.checks_failed
print("\nAudit outcome: trace REJECTED — modification detected before regulatory submission.")
```

**What this proves:** Without notarize, audit traces are just JSON files anyone can edit. With hash-chained Merkle roots, any modification — even changing a single character — breaks the verification and is immediately detectable.

---

## GitHub Topics

Suggested topics for discoverability:

`ai-agents` `trace-verification` `attestation` `eu-ai-act` `compliance` `audit` `hash-chain` `merkle-tree` `pii-scrubbing` `sqlite` `mcp` `openai` `llm-tools` `llmops` `python`

---

[![Star History Chart](https://api.star-history.com/svg?repos=sandeep-alluru/notarize&type=Date)](https://star-history.com/#sandeep-alluru/notarize&Date)
