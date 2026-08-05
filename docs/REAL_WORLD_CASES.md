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

## Related queue IDs

- **SILENT-SUCCESS** — this case (P0)
- **D-GCROOT** (groundcrew) — success with 0 files / phantom paths
- Empty-trace FAIL_LOUD — prior closed-loop work on `gate_trace`
