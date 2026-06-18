"""SQLite-backed store for AgentTrace and VerificationResult objects."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from notarize.trace import AgentTrace
from notarize.verifier import VerificationResult


class TraceStore:
    """SQLite-backed store for traces and verification results.

    All traces and results are stored in a single SQLite database.
    Deduplication is by trace_id for traces and by id for results.

    Attributes:
        path: Path to the SQLite database file.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS traces (
        id TEXT NOT NULL,
        trace_id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        task TEXT NOT NULL,
        merkle_root TEXT NOT NULL,
        created_at REAL NOT NULL,
        data TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS results (
        id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        verdict TEXT NOT NULL,
        timestamp REAL NOT NULL,
        data TEXT NOT NULL
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def save_trace(self, trace: AgentTrace) -> None:
        """Store an AgentTrace (upsert by trace_id).

        Args:
            trace: The AgentTrace to save.
        """
        self._conn.execute(
            """INSERT OR REPLACE INTO traces
               (id, trace_id, agent_name, task, merkle_root, created_at, data)
               VALUES (?,?,?,?,?,?,?)""",
            (
                trace.id,
                trace.trace_id,
                trace.agent_name,
                trace.task,
                trace.merkle_root,
                trace.created_at,
                json.dumps(trace.to_dict()),
            ),
        )
        self._conn.commit()

    def get_trace(self, trace_id: str) -> AgentTrace | None:
        """Retrieve an AgentTrace by trace_id, or None if not found.

        Args:
            trace_id: The user-provided trace identifier.

        Returns:
            The AgentTrace, or None.
        """
        row = self._conn.execute("SELECT data FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
        if row is None:
            return None
        return AgentTrace.from_dict(json.loads(row["data"]))

    def list_traces(self) -> list[AgentTrace]:
        """Return all stored AgentTrace objects ordered by created_at.

        Returns:
            List of AgentTrace objects, oldest first.
        """
        rows = self._conn.execute("SELECT data FROM traces ORDER BY created_at").fetchall()
        return [AgentTrace.from_dict(json.loads(r["data"])) for r in rows]

    def save_result(self, result: VerificationResult) -> None:
        """Store a VerificationResult (upsert by id).

        Args:
            result: The VerificationResult to save.
        """
        self._conn.execute(
            """INSERT OR REPLACE INTO results
               (id, trace_id, verdict, timestamp, data)
               VALUES (?,?,?,?,?)""",
            (
                result.id,
                result.trace_id,
                result.verdict,
                result.timestamp,
                json.dumps(result.to_dict()),
            ),
        )
        self._conn.commit()

    def get_result(self, result_id: str) -> VerificationResult | None:
        """Retrieve a VerificationResult by id, or None if not found.

        Args:
            result_id: The content-addressed result ID.

        Returns:
            The VerificationResult, or None.
        """
        row = self._conn.execute("SELECT data FROM results WHERE id=?", (result_id,)).fetchone()
        if row is None:
            return None
        return VerificationResult.from_dict(json.loads(row["data"]))

    def list_results(self) -> list[VerificationResult]:
        """Return all stored VerificationResult objects ordered by timestamp.

        Returns:
            List of VerificationResult objects, oldest first.
        """
        rows = self._conn.execute("SELECT data FROM results ORDER BY timestamp").fetchall()
        return [VerificationResult.from_dict(json.loads(r["data"])) for r in rows]

    def __enter__(self) -> TraceStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
