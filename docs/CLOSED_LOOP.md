# Closed loop — `notarize`

**Status:** reader wired (eagle-eyes / 2026-08-04)  
**Owner loop:** L4/L5

## Load-bearing job

Canonical hash-chained execution traces + verify

## Who reads the output?

- Library API: `notarize.gate_trace` / `assert_trace_verified` (`closed_loop.py`)
- Underlying checks: `ConsistencyVerifier`
- CI / eagle-eyes `dogfood_verify` act on `exit_code` (empty → FAIL_LOUD)

## What outcome changes?

Fail tick if verify fails; empty write-only log is **FAIL_LOUD** (exit 2), never silent pass

## When NOT to use (anti-ornament)

Write-only logging with no verify is ornament

## Non-Ornament checklist

- [x] Reader implemented in CI, gate, or eagle-eyes script (`gate_trace` + tests)
- [x] Empty/wrong output fails loudly (`FAIL_LOUD`, exit 2)
- [x] Not exposed as free MCP in product agents (import/CI gate only)
- [ ] Linked gap IDs in mem0 when improving

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

Prefer small daily commits that raise scorer pillars or finish remaining checkboxes.

## Reader wiring (2026-08-04)

- [x] Documented load-bearing job
- [x] Library closed-loop gate rejects empty traces (stricter than raw verifier)
- [x] eagle-eyes `scripts/dogfood_verify.py` exercises real `gate_trace`
- [ ] CI job invokes gate on every PR (next)

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2
