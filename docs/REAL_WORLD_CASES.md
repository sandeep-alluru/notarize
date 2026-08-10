# Real-world cases driving notarize

Mined from farm_memory (Qdrant), Foundry pipeline lessons, and public research
(eagle-eyes Track B).

## Case SILENT-SUCCESS (farm) — CRITICAL

**Source:** eagle-eyes `REAL_WORK_QUEUE` P0; Foundry-class *assemble exits 0
degraded* — process reports success while work is incomplete or failed.

**What failed:**

Pipelines (and agents) often:

1. Write a hash-valid execution trace (or skip integrity entirely).
2. Exit with code **0** / `success=True`.
3. Leave **failed** or **degraded** steps in the trace (`result=error`,
   `result=degraded`, observation text *partially complete / missing artifacts*).

A gate that only checks *empty vs non-empty* or *hash chain intact* **passes**
and hides the lie. Downstream consumers treat the run as good.

Related farm patterns: D-GCROOT phantom success paths (groundcrew), swallowed
exceptions that disable features without failing the job.

**Public twins:**

| Case | Mapping |
|------|---------|
| DiagChain (arXiv 2608.03591) | Intermediate failures must surface, not only final output |
| MAFIA (arXiv 2608.03844) | Audit/memory must not green-light bad trajectories |
| TraceCompiler (arXiv 2608.02680) | Trace mining assumes honest step outcomes |

**Product fix in this repo:**

| Control | API |
|---------|-----|
| Detect failed steps | `step_is_failed` / `failed_step_indices` |
| Detect degraded steps | `step_is_degraded` / `degraded_step_indices` |
| Chain OK but bad steps | `gate_trace` (default `refuse_failed_steps` / `refuse_degraded`) |
| Claim vs reality | `gate_claimed_success(claimed_ok, exit_code, trace)` |
| Raise form | `assert_no_silent_success(...)` |

**Tests:** `tests/test_silent_success.py`

**Non-Ornament:** Publish / assemble CI must call `gate_claimed_success` (or
`gate_trace` with defaults) and refuse when `ok is False`. Integrity alone is
not a success gate.

---

## Case TRACE-COMPILE — TraceCompiler workflow mining (arXiv 2608.02680)

**Source:** Track B research (`20260808T121224Z`) —
[TraceCompiler: Skill-Guided Mining and Compilation of LLM Agent Traces](https://arxiv.org/abs/2608.02680).

**What fails:**

1. Agents re-discover procedures already executed; traces mix reusable structure
   with retries, exploration, accidental ordering.
2. “Compiled” skills claim hard ordering without **unique** producer→consumer
   attribution (no auditable evidence).
3. Pure residual-LLM graphs are promoted as deterministic workflows.

**Product in this repo:**

| Control | API |
|---------|-----|
| Invocation / edge types | `ToolInvocation`, `WorkflowEdge`, `CompiledWorkflow` |
| Deterministic miner | `compile_trace_workflow` (unique copy → hard edge) |
| Evidence check | `hard_edges_missing_evidence` |
| Gate | `gate_compiled_workflow(...)` |
| Raise form | `assert_compiled_workflow_ok(...)` |

**Rules (load-bearing):**

- Empty workflow when required → **FAIL_LOUD**
- Hard edge without evidence tuple → **FAIL_LOUD**
- `require_hard_edges` / `min_hard_edges` unmet → **FAIL**
- All edges `llm_residual` → **FAIL**
- Residual ratio > `max_residual_ratio` → **FAIL**
- Suspected edges do **not** impose hard ordering
- Hard edges with evidence → **PASS**

**Tests:** `tests/test_trace_compile.py`

**Non-Ornament:** Call `gate_compiled_workflow` before promoting a mined skill
to production replay. Pair with `gate_claimed_success` for step honesty.

---

## Case TRIAGE-SPLIT — multi-agent audit capacity / bias (arXiv 2608.06949)

**Source:** Track B research (`20260810T201238Z`) —
[Does Splitting a Triage Decision Across Agents Hide Bias or Help Catch
It?](https://arxiv.org/abs/2608.06949v1).

**What fails:**

1. Life/resource allocation is split across assessment → allocation → audit,
   but **audit is missing** or **non-independent**.
2. Same agent collapses multiple roles; bias is not caught.
3. Clinically identical paired cases diverge only on demographics while the
   pipeline still claims “audited fair”.
4. `gate_claimed_success` checks step honesty, not **pipeline role integrity**.

**Product in this repo:**

| Control | API |
|---------|-----|
| Stage / pair types | `TriageStage`, `PairedTriageCase` |
| Analyzer | `analyze_triage_pipeline` → `TriageAuditReport` |
| Gate | `gate_triage_audit(...)` |
| Raise form | `assert_triage_audit_ok` |

**Rules (load-bearing):**

- claim audited + empty stages → **FAIL_LOUD**
- missing assessment/allocation/audit roles when claiming full pipeline → **FAIL**
- allocation without audit stage → **FAIL**
- non-independent / same-agent role collapse → **FAIL**
- clinically identical demographic pairs with different decisions → **FAIL**
- independent full pipeline + consistent pairs → **PASS**

**Tests:** `tests/test_triage_audit.py`

**Non-Ornament:** Call `gate_triage_audit` before accepting multi-agent
resource-allocation outcomes as audited. Pair with `gate_claimed_success`.

---

## Related queue IDs

- **SILENT-SUCCESS** — degraded/failed steps claim success (P0)
- **TRACE-COMPILE** — TraceCompiler class
- **TRIAGE-SPLIT** — multi-agent audit capacity / bias (this section)
- **D-GCROOT** (groundcrew) — success with 0 files / phantom paths
- Empty-trace FAIL_LOUD — prior closed-loop work on `gate_trace`
