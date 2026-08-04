# Closed loop — `notarize`

**Status:** stub (eagle-eyes Phase 0 / 2026-08-04)  
**Owner loop:** L4/L5

## Load-bearing job

Canonical hash-chained execution traces + verify

## Who reads the output?

Verifier in L4/L5; audit storage rejects tampered traces

## What outcome changes?

Fail tick if verify fails; dogfood every improve session

## When NOT to use (anti-ornament)

Write-only logging with no verify is ornament

## Non-Ornament checklist

- [ ] Reader implemented in CI, gate, or eagle-eyes script
- [ ] Empty/wrong output fails loudly
- [ ] Not exposed as free MCP in product agents
- [ ] Linked gap IDs in mem0 when improving

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

This file exists so pillar **C (closed loop)** can rise with real wiring over time. Prefer small daily commits that move a checkbox toward done.

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Reader wiring (2026-08-04)

- [x] Documented load-bearing job
- [x] eagle-eyes `scripts/dogfood_verify.py` exercises hash-chain FAIL_LOUD pattern
- [ ] CI job invokes gate on every PR (next)
- Auto pytest stamps recorded under eagle-eyes/state/
