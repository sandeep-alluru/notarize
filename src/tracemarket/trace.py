"""TraceStep and AgentTrace data models for hash-chained agent execution traces."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


def _sha16(text: str) -> str:
    """Return the first 16 hex chars of SHA-256(text)."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class TraceStep:
    """A single step in an agent execution trace.

    Steps are content-addressed by their step_index, action, observation, and result.
    Each step points to the previous step's ID via parent_id, forming a hash chain.

    Attributes:
        step_index: Zero-based index of this step in the trace.
        action: What the agent did (e.g. "tool_call:search").
        observation: What the agent observed.
        result: What happened (e.g. "success", "error").
        tool_name: Optional tool name used in this step.
        timestamp: Unix timestamp of this step.
        id: SHA-256[:16] of "step_index|action|observation|result".
        parent_id: The previous step's ID, or None for the first step.
    """

    step_index: int
    action: str
    observation: str
    result: str
    tool_name: str = ""
    timestamp: float = field(default_factory=time.time)
    id: str = field(init=False)
    parent_id: str | None = None

    def __post_init__(self) -> None:
        self.id = _sha16(f"{self.step_index}|{self.action}|{self.observation}|{self.result}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "step_index": self.step_index,
            "action": self.action,
            "observation": self.observation,
            "result": self.result,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
            "id": self.id,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TraceStep:
        """Deserialize from a dict produced by to_dict()."""
        step = cls(
            step_index=d["step_index"],
            action=d["action"],
            observation=d["observation"],
            result=d["result"],
            tool_name=d.get("tool_name", ""),
            timestamp=d.get("timestamp", 0.0),
        )
        step.parent_id = d.get("parent_id")
        return step

    def __repr__(self) -> str:
        return f"TraceStep({self.id!r}: [{self.step_index}] {self.action!r} -> {self.result!r})"


@dataclass
class AgentTrace:
    """A hash-chained sequence of TraceSteps with a Merkle root.

    The steps form a linked chain where each step's parent_id points to the
    previous step's id. A Merkle root is computed from all step IDs to enable
    tamper detection.

    Attributes:
        trace_id: User-provided trace identifier.
        agent_name: Name of the agent that produced this trace.
        task: What the agent was asked to do.
        steps: Ordered list of TraceStep objects.
        merkle_root: SHA-256[:16] of the sorted step IDs.
        created_at: Unix timestamp when this trace was created.
        id: SHA-256[:16] of "trace_id|agent_name|task|merkle_root".
    """

    trace_id: str
    agent_name: str
    task: str
    steps: list[TraceStep]
    merkle_root: str = field(init=False)
    created_at: float = field(default_factory=time.time)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        # Build hash chain: each step's parent_id = previous step's id
        for i, step in enumerate(self.steps):
            if i == 0:
                step.parent_id = None
            else:
                step.parent_id = self.steps[i - 1].id

        # Compute merkle_root from sorted step IDs
        step_ids = sorted(s.id for s in self.steps)
        self.merkle_root = _sha16("|".join(step_ids)) if step_ids else _sha16("")

        # Compute trace id
        self.id = _sha16(f"{self.trace_id}|{self.agent_name}|{self.task}|{self.merkle_root}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "merkle_root": self.merkle_root,
            "created_at": self.created_at,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentTrace:
        """Deserialize from a dict produced by to_dict()."""
        steps = [TraceStep.from_dict(s) for s in d.get("steps", [])]
        trace = cls(
            trace_id=d["trace_id"],
            agent_name=d["agent_name"],
            task=d["task"],
            steps=steps,
            created_at=d.get("created_at", 0.0),
        )
        return trace

    def __repr__(self) -> str:
        return (
            f"AgentTrace({self.id!r}: {self.trace_id!r}, "
            f"{len(self.steps)} steps, agent={self.agent_name!r})"
        )
