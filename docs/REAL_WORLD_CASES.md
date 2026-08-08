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

## Related queue IDs

- **SILENT-SUCCESS** — this case (P0)
- **TRACE-COMPILE** — TraceCompiler class (this section)
- **D-GCROOT** (groundcrew) — success with 0 files / phantom paths
- Empty-trace FAIL_LOUD — prior closed-loop work on `gate_trace`
