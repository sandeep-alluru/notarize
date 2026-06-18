"""PrivacyScrubber for structure-preserving PII redaction from agent traces."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from notarize.trace import AgentTrace


@dataclass
class ScrubResult:
    """Result of scrubbing PII from a trace.

    Attributes:
        original_trace_id: The trace_id of the original (pre-scrub) trace.
        scrubbed_trace: A deep-copied AgentTrace with PII replaced.
        replacements_count: Total number of replacements made.
        patterns_matched: List of pattern names that were triggered.
    """

    original_trace_id: str
    scrubbed_trace: AgentTrace
    replacements_count: int
    patterns_matched: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "original_trace_id": self.original_trace_id,
            "scrubbed_trace": self.scrubbed_trace.to_dict(),
            "replacements_count": self.replacements_count,
            "patterns_matched": self.patterns_matched,
        }


# PII patterns: (name, compiled regex, replacement)
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "email",
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE),
        "[EMAIL_REDACTED]",
    ),
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)",
        ),
        "[PHONE_REDACTED]",
    ),
    (
        "credit_card",
        re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "[CREDIT_CARD_REDACTED]",
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[SSN_REDACTED]",
    ),
    (
        "ip_address",
        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
        "[IP_REDACTED]",
    ),
]


class PrivacyScrubber:
    """Structure-preserving PII redaction for agent traces.

    Scrubs the following PII patterns from step action, observation, and result fields:
    - Email addresses → [EMAIL_REDACTED]
    - Phone numbers → [PHONE_REDACTED]
    - Credit card numbers → [CREDIT_CARD_REDACTED]
    - Social Security Numbers → [SSN_REDACTED]
    - IP addresses → [IP_REDACTED]
    """

    def scrub(self, trace: AgentTrace) -> ScrubResult:
        """Scrub PII from a trace's step fields.

        Deep-copies the trace before modification to preserve the original.

        Args:
            trace: The AgentTrace to scrub.

        Returns:
            A ScrubResult containing the scrubbed trace and replacement statistics.
        """
        scrubbed = copy.deepcopy(trace)
        total_replacements = 0
        matched_patterns: set[str] = set()

        for step in scrubbed.steps:
            for field_name in ("action", "observation", "result", "tool_name"):
                text = getattr(step, field_name)
                if not text:
                    continue
                new_text, count, patterns = _scrub_text(text)
                if count > 0:
                    setattr(step, field_name, new_text)
                    total_replacements += count
                    matched_patterns.update(patterns)

        # Recompute the trace IDs since content changed
        # Re-build the chain by reconstructing
        from notarize.trace import AgentTrace as _AgentTrace

        rebuilt = _AgentTrace(
            trace_id=scrubbed.trace_id,
            agent_name=scrubbed.agent_name,
            task=scrubbed.task,
            steps=scrubbed.steps,
            created_at=scrubbed.created_at,
        )

        return ScrubResult(
            original_trace_id=trace.trace_id,
            scrubbed_trace=rebuilt,
            replacements_count=total_replacements,
            patterns_matched=sorted(matched_patterns),
        )


def _scrub_text(text: str) -> tuple[str, int, list[str]]:
    """Apply all PII patterns to a text string.

    Returns:
        A tuple of (scrubbed_text, replacement_count, patterns_matched).
    """
    count = 0
    patterns_hit: list[str] = []

    for pattern_name, pattern, replacement in _PATTERNS:
        new_text, n = pattern.subn(replacement, text)
        if n > 0:
            text = new_text
            count += n
            patterns_hit.append(pattern_name)

    return text, count, patterns_hit
