"""FastAPI REST wrapper for tracemarket.

Start:   uvicorn tracemarket.api:app --reload
Install: pip install "tracemarket[api]"
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:
    raise ImportError("API server requires: pip install 'tracemarket[api]'") from exc

from tracemarket import __version__
from tracemarket.scrubber import PrivacyScrubber
from tracemarket.store import TraceStore
from tracemarket.trace import AgentTrace
from tracemarket.verifier import ConsistencyVerifier

_DEFAULT_DB = ".tracemarket/traces.db"

app = FastAPI(
    title="tracemarket API",
    description="Canonical trace format and verifier for agent execution attestation.",
    version=__version__,
    license_info={
        "name": "MIT",
        "url": "https://github.com/sandeep-alluru/tracemarket/blob/main/LICENSE",
    },
)


class VerifyRequest(BaseModel):
    """Request body for POST /verify."""

    trace: dict[str, Any] = Field(..., description="AgentTrace as a JSON dict.")
    db: str = Field(_DEFAULT_DB, description="Path to the tracemarket database.")


class ScrubRequest(BaseModel):
    """Request body for POST /scrub."""

    trace: dict[str, Any] = Field(..., description="AgentTrace as a JSON dict.")


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.post("/verify")
async def verify_trace(request: VerifyRequest) -> Any:
    """Verify an AgentTrace for internal consistency."""
    try:
        trace = AgentTrace.from_dict(request.trace)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid trace format: {exc}") from exc

    verifier = ConsistencyVerifier()
    result = verifier.verify(trace)

    with TraceStore(request.db) as store:
        store.save_trace(trace)
        store.save_result(result)

    return result.to_dict()


@app.post("/scrub")
async def scrub_trace(request: ScrubRequest) -> Any:
    """Scrub PII from an AgentTrace."""
    try:
        trace = AgentTrace.from_dict(request.trace)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid trace format: {exc}") from exc

    scrubber = PrivacyScrubber()
    result = scrubber.scrub(trace)

    return {
        "original_trace_id": result.original_trace_id,
        "scrubbed_trace": result.scrubbed_trace.to_dict(),
        "replacements_count": result.replacements_count,
        "patterns_matched": result.patterns_matched,
    }


@app.get("/traces")
async def list_traces(db: str = _DEFAULT_DB) -> Any:
    """Return all stored traces."""
    with TraceStore(db) as store:
        traces = store.list_traces()
    return {"traces": [t.to_dict() for t in traces]}


@app.get("/trace/{trace_id}")
async def get_trace(trace_id: str, db: str = _DEFAULT_DB) -> Any:
    """Return a specific trace by trace_id."""
    with TraceStore(db) as store:
        trace = store.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace not found: {trace_id}")
    return trace.to_dict()
