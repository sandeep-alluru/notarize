# tracemarket — Session Anchor

**Research spec:** `../tech-research/02-Verification-Provenance-and-Audit/tracemarket-the-open-protocol-and-marketplace-for-verifi/README.md`  
**One-liner:** Open protocol for verified agentic execution traces — canonicalize, scrub, hash, publish  
**Phase:** backlog  
**Stack:** Python, FastAPI, Pydantic, hashlib (stdlib)  

## Key decisions
<!-- fill in as decisions are made during build sessions -->

## Next step
Read the research spec, then design the canonical trace JSON schema.

## MVP definition
- `pip install tracemarket` works
- JSON schema for canonical agent trace format
- Python library: trace normalization + privacy scrubbing + content-hash generation
- CLI: `tracemarket submit trace.json`, `tracemarket verify <hash>`
- FastAPI reference server (SQLite backend)
- Adapter: ingest a LangSmith export → TraceMarket format
- README with schema diagram and quickstart
