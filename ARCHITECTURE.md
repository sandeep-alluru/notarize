# notarize Architecture

This document is the authoritative developer reference for notarize's internals. It covers the data flow, module responsibilities, key invariants, the SQLite schema, and the verification algorithm.

---

## Data Flow

```
┌─────────────┐   TraceStep(step_index, action,   ┌──────────────┐
│    Agent    │   observation, result)             │  AgentTrace  │
│  (or CLI)   │ ───────────────────────────────►   │  hash chain  │
└─────────────┘                                    │              │
                                                   │  steps[0]    │
                                                   │  parent=None │
                                                   │  steps[1]    │
                                                   │  parent=s[0] │
                                                   │  ...         │
                                                   │              │
                                                   │  merkle_root │
                                                   │  trace.id    │
                                                   └──────────────┘
                                                          │
                                              ConsistencyVerifier
                                                          │
                                                          ▼
                                                   ┌──────────────┐
                                                   │ Verification │
                                                   │ Result       │
                                                   │ verified /   │
                                                   │ tampered /   │
                                                   │ invalid      │
                                                   └──────────────┘
                                                          │
                                                    TraceStore
                                                    (SQLite)
```

**Sequence:**

1. Agent produces `TraceStep` objects for each action it takes.
2. Steps are assembled into an `AgentTrace` — `__post_init__` builds the hash chain and computes the Merkle root.
3. `ConsistencyVerifier.verify()` checks the chain, root, indices, duplicates, and trace ID.
4. `PrivacyScrubber.scrub()` deep-copies the trace and redacts PII patterns.
5. `TraceStore` persists traces and results in SQLite.

---

## Module Map

| File | Responsibility |
|------|---------------|
| `trace.py` | `TraceStep`, `AgentTrace` dataclasses. Hash chain and Merkle root logic. `_sha16()` helper. |
| `verifier.py` | `ConsistencyVerifier`, `VerificationResult`. Five-check verification algorithm. |
| `scrubber.py` | `PrivacyScrubber`, `ScrubResult`. Regex-based PII redaction across step fields. |
| `store.py` | `TraceStore` — SQLite-backed persistence for traces and results. |
| `report.py` | Output formatters: `print_result()`, `print_trace()`, `to_json()`, `to_markdown()`. |
| `cli.py` | Click CLI. Subcommands: `verify`, `scrub`, `log`, `status`. Reads `--db` from context. |
| `api.py` | FastAPI REST server. Endpoints: `/health`, `/verify`, `/scrub`, `/traces`, `/trace/{id}`. |
| `mcp_server.py` | Model Context Protocol server. Tools: `verify_trace`, `scrub_trace`, `list_traces`. |

---

## Key Invariants

### 1. TraceStep.id is deterministic

```
TraceStep.id = SHA-256[:16]("{step_index}|{action}|{observation}|{result}")
```

The same tuple always produces the same 16-character hex ID. `tool_name` and `timestamp` are **not** part of the ID — they are metadata, not identity.

### 2. Hash chain: parent_id links

```
steps[0].parent_id = None
steps[i].parent_id = steps[i-1].id  (for i > 0)
```

This creates a tamper-evident chain: modifying any step's content changes its ID, which breaks the next step's `parent_id` pointer. The `ConsistencyVerifier` detects this.

### 3. Merkle root seals the full trace

```
AgentTrace.merkle_root = SHA-256[:16]("|".join(sorted(step.id for step in steps)))
```

Sorting ensures the root is independent of step order in memory, while still reflecting the set of steps. Adding, removing, or modifying any step changes the root.

### 4. AgentTrace.id is content-addressed

```
AgentTrace.id = SHA-256[:16]("{trace_id}|{agent_name}|{task}|{merkle_root}")
```

The trace ID is derived from the trace's identity fields and its Merkle root. Changing any of these invalidates the stored `id`.

### 5. from_dict() re-runs __post_init__

`AgentTrace.from_dict()` reconstructs the object from a dict, which triggers `__post_init__` again. This means the hash chain and Merkle root are always recomputed from the step content — you cannot smuggle in a tampered root via serialization.

---

## SQLite Schema

```sql
-- Agent execution traces
CREATE TABLE traces (
    id          TEXT NOT NULL,       -- AgentTrace.id (content-addressed)
    trace_id    TEXT PRIMARY KEY,    -- User-provided trace identifier
    agent_name  TEXT NOT NULL,
    task        TEXT NOT NULL,
    merkle_root TEXT NOT NULL,
    created_at  REAL NOT NULL,
    data        TEXT NOT NULL        -- Full JSON serialization
);

-- Verification results
CREATE TABLE results (
    id          TEXT PRIMARY KEY,    -- VerificationResult.id (content-addressed)
    trace_id    TEXT NOT NULL,       -- References traces.trace_id
    verdict     TEXT NOT NULL,       -- 'verified' | 'consistent' | 'tampered' | 'invalid'
    timestamp   REAL NOT NULL,
    data        TEXT NOT NULL        -- Full JSON serialization
);
```

**Notes:**
- Traces are upserted by `trace_id` (not by `id`) — re-verifying the same trace ID overwrites the stored trace.
- The full JSON is stored in `data` to avoid schema migrations as the model evolves.
- `TraceStore` is not thread-safe — use one store per process.

---

## Verification Algorithm

```python
def verify(trace: AgentTrace) -> VerificationResult:
    checks_passed = []
    checks_failed = []

    # 1. Hash chain integrity
    for i, step in enumerate(trace.steps):
        if i == 0:
            assert step.parent_id is None
        else:
            assert step.parent_id == trace.steps[i-1].id

    # 2. Merkle root
    computed = SHA-256[:16]("|".join(sorted(s.id for s in trace.steps)))
    assert computed == trace.merkle_root

    # 3. Monotonic step indices
    assert steps[0].step_index == 0
    for i in range(1, len(steps)):
        assert steps[i].step_index == steps[i-1].step_index + 1

    # 4. No duplicate step IDs
    assert len(set(s.id for s in steps)) == len(steps)

    # 5. Trace ID matches
    computed_id = SHA-256[:16](f"{trace_id}|{agent_name}|{task}|{merkle_root}")
    assert computed_id == trace.id

    # Verdict
    if not checks_failed:   return "verified"
    if chain or root failed: return "tampered"
    return "consistent"
```

**Verdict logic:**
- `verified` — all 5 checks pass
- `tampered` — hash chain or Merkle root check failed (structural tampering detected)
- `consistent` — other checks failed (e.g. non-monotonic indices, wrong trace.id) but chain is intact
- `invalid` — an unexpected exception occurred during verification

---

## PII Scrubbing Patterns

| Pattern | Regex | Replacement |
|---------|-------|-------------|
| Email | `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` | `[EMAIL_REDACTED]` |
| Phone | `(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}` | `[PHONE_REDACTED]` |
| Credit card | `(?:\d{4}[-\s]?){3}\d{4}` | `[CREDIT_CARD_REDACTED]` |
| SSN | `\d{3}-\d{2}-\d{4}` | `[SSN_REDACTED]` |
| IP address | `(?:\d{1,3}\.){3}\d{1,3}` | `[IP_REDACTED]` |

Scrubbing deep-copies the trace before modification (the original is never mutated). After scrubbing, the hash chain and Merkle root are recomputed from the redacted content.

---

## Extension Points

- **Custom PII patterns** — add entries to `_PATTERNS` in `scrubber.py`.
- **Additional verification checks** — extend `ConsistencyVerifier.verify()` with new checks.
- **Remote store** — implement the same `save_trace` / `get_trace` interface against a remote database.
- **Async API** — replace `TraceStore` with an async SQLite adapter for use in async agent frameworks.
- **Signature attestation** — extend `AgentTrace` with a cryptographic signature over `trace.id`.
