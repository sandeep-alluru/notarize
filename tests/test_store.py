"""Tests for TraceStore from tracemarket.store."""

from __future__ import annotations

import pytest

from tracemarket.store import TraceStore
from tracemarket.trace import AgentTrace, TraceStep
from tracemarket.verifier import ConsistencyVerifier, VerificationResult


@pytest.fixture
def store(tmp_path: pytest.TempPathFactory) -> TraceStore:
    s = TraceStore(str(tmp_path / "traces.db"))
    yield s
    s.close()


def _make_trace(trace_id: str = "t1", n_steps: int = 2) -> AgentTrace:
    steps = [TraceStep(i, f"action_{i}", f"obs_{i}", "success") for i in range(n_steps)]
    return AgentTrace(trace_id, "agent", "task", steps, created_at=float(hash(trace_id) % 1000))


def _make_result(trace_id: str = "t1", verdict: str = "verified") -> VerificationResult:
    return VerificationResult(trace_id, verdict, ["check_a"], [], None, 100.0)


# ── TraceStore construction ───────────────────────────────────────────────────


def test_tracestore_creates_file(tmp_path: pytest.TempPathFactory) -> None:
    db = tmp_path / "traces.db"
    s = TraceStore(str(db))
    s.close()
    assert db.exists()


def test_tracestore_creates_parent_dirs(tmp_path: pytest.TempPathFactory) -> None:
    db = tmp_path / "nested" / "dir" / "traces.db"
    s = TraceStore(str(db))
    s.close()
    assert db.exists()


def test_tracestore_context_manager(tmp_path: pytest.TempPathFactory) -> None:
    db = tmp_path / "traces.db"
    with TraceStore(str(db)) as store:
        assert store is not None


# ── save_trace / get_trace ────────────────────────────────────────────────────


def test_save_and_get_trace(store: TraceStore) -> None:
    trace = _make_trace("t1")
    store.save_trace(trace)
    retrieved = store.get_trace("t1")
    assert retrieved is not None
    assert retrieved.trace_id == "t1"
    assert retrieved.agent_name == "agent"


def test_get_trace_missing_returns_none(store: TraceStore) -> None:
    assert store.get_trace("nonexistent") is None


def test_save_trace_upsert(store: TraceStore) -> None:
    """Saving the same trace_id twice should update (upsert)."""
    trace = _make_trace("t1")
    store.save_trace(trace)
    store.save_trace(trace)
    traces = store.list_traces()
    assert len([t for t in traces if t.trace_id == "t1"]) == 1


def test_save_trace_preserves_steps(store: TraceStore) -> None:
    trace = _make_trace("t1", n_steps=3)
    store.save_trace(trace)
    retrieved = store.get_trace("t1")
    assert retrieved is not None
    assert len(retrieved.steps) == 3


# ── list_traces ───────────────────────────────────────────────────────────────


def test_list_traces_empty(store: TraceStore) -> None:
    assert store.list_traces() == []


def test_list_traces_multiple(store: TraceStore) -> None:
    store.save_trace(_make_trace("t1"))
    store.save_trace(_make_trace("t2"))
    traces = store.list_traces()
    assert len(traces) == 2
    trace_ids = {t.trace_id for t in traces}
    assert "t1" in trace_ids
    assert "t2" in trace_ids


# ── save_result / get_result ──────────────────────────────────────────────────


def test_save_and_get_result(store: TraceStore) -> None:
    result = _make_result("t1", "verified")
    store.save_result(result)
    retrieved = store.get_result(result.id)
    assert retrieved is not None
    assert retrieved.verdict == "verified"
    assert retrieved.trace_id == "t1"


def test_get_result_missing_returns_none(store: TraceStore) -> None:
    assert store.get_result("nonexistent") is None


def test_save_result_upsert(store: TraceStore) -> None:
    result = _make_result("t1")
    store.save_result(result)
    store.save_result(result)
    results = store.list_results()
    assert len([r for r in results if r.id == result.id]) == 1


# ── list_results ──────────────────────────────────────────────────────────────


def test_list_results_empty(store: TraceStore) -> None:
    assert store.list_results() == []


def test_list_results_multiple(store: TraceStore) -> None:
    r1 = _make_result("t1", "verified")
    r2 = _make_result("t2", "tampered")
    store.save_result(r1)
    store.save_result(r2)
    results = store.list_results()
    assert len(results) == 2
    verdicts = {r.verdict for r in results}
    assert "verified" in verdicts
    assert "tampered" in verdicts


# ── Integration: verify + store ───────────────────────────────────────────────


def test_verify_and_store_roundtrip(tmp_path: pytest.TempPathFactory) -> None:
    trace = _make_trace("t-verify", 3)
    verifier = ConsistencyVerifier()
    result = verifier.verify(trace)

    with TraceStore(str(tmp_path / "traces.db")) as store:
        store.save_trace(trace)
        store.save_result(result)
        retrieved_trace = store.get_trace("t-verify")
        retrieved_result = store.get_result(result.id)

    assert retrieved_trace is not None
    assert retrieved_result is not None
    assert retrieved_result.verdict == "verified"
