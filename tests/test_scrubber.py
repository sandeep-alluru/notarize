"""Tests for PrivacyScrubber and ScrubResult from notarize.scrubber."""

from __future__ import annotations

import pytest

from notarize.scrubber import PrivacyScrubber, _scrub_text
from notarize.trace import AgentTrace, TraceStep


@pytest.fixture
def scrubber() -> PrivacyScrubber:
    return PrivacyScrubber()


def _make_trace(action: str = "", observation: str = "", result: str = "") -> AgentTrace:
    steps = [TraceStep(0, action, observation, result)]
    return AgentTrace("scrub-001", "test-agent", "test task", steps, created_at=0.0)


# ── _scrub_text helper ────────────────────────────────────────────────────────


def test_scrub_text_replaces_email() -> None:
    text, count, patterns = _scrub_text("Contact user@example.com now")
    assert "[EMAIL_REDACTED]" in text
    assert count == 1
    assert "email" in patterns


def test_scrub_text_replaces_phone() -> None:
    text, count, patterns = _scrub_text("Call me at 555-123-4567 please")
    assert "[PHONE_REDACTED]" in text
    assert count >= 1
    assert "phone" in patterns


def test_scrub_text_replaces_credit_card() -> None:
    text, count, patterns = _scrub_text("Card: 4111-1111-1111-1111")
    assert "[CREDIT_CARD_REDACTED]" in text
    assert count == 1
    assert "credit_card" in patterns


def test_scrub_text_replaces_ssn() -> None:
    text, count, patterns = _scrub_text("SSN is 123-45-6789")
    assert "[SSN_REDACTED]" in text
    assert count == 1
    assert "ssn" in patterns


def test_scrub_text_replaces_ip_address() -> None:
    text, count, patterns = _scrub_text("Server at 192.168.1.100 is down")
    assert "[IP_REDACTED]" in text
    assert count == 1
    assert "ip_address" in patterns


def test_scrub_text_no_pii() -> None:
    text, count, patterns = _scrub_text("No personal data here")
    assert count == 0
    assert patterns == []
    assert text == "No personal data here"


def test_scrub_text_multiple_pii() -> None:
    text, count, patterns = _scrub_text("Email: a@b.com and IP: 10.0.0.1")
    assert "[EMAIL_REDACTED]" in text
    assert "[IP_REDACTED]" in text
    assert count == 2
    assert "email" in patterns
    assert "ip_address" in patterns


# ── PrivacyScrubber.scrub ─────────────────────────────────────────────────────


def test_scrub_removes_email(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(action="Send to alice@example.com", observation="sent", result="success")
    result = scrubber.scrub(trace)
    assert result.replacements_count >= 1
    assert "email" in result.patterns_matched
    assert "alice@example.com" not in result.scrubbed_trace.steps[0].action


def test_scrub_removes_phone(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(observation="Called 415-555-0100 for verification")
    result = scrubber.scrub(trace)
    assert result.replacements_count >= 1
    assert "phone" in result.patterns_matched


def test_scrub_removes_ssn(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(result="SSN 999-88-7777 verified")
    result = scrubber.scrub(trace)
    assert result.replacements_count >= 1
    assert "ssn" in result.patterns_matched


def test_scrub_removes_ip(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(observation="Connected to 10.20.30.40")
    result = scrubber.scrub(trace)
    assert result.replacements_count >= 1
    assert "ip_address" in result.patterns_matched


def test_scrub_preserves_original_trace(scrubber: PrivacyScrubber) -> None:
    """Original trace must not be modified."""
    trace = _make_trace(action="Email user@test.com")
    original_action = trace.steps[0].action
    scrubber.scrub(trace)
    assert trace.steps[0].action == original_action


def test_scrub_no_pii_returns_zero_replacements(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(action="Search web", observation="Found results", result="success")
    result = scrubber.scrub(trace)
    assert result.replacements_count == 0
    assert result.patterns_matched == []


def test_scrub_result_original_trace_id(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace()
    result = scrubber.scrub(trace)
    assert result.original_trace_id == "scrub-001"


def test_scrub_result_scrubbed_trace_is_agenttrace(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(action="Send to user@example.com")
    result = scrubber.scrub(trace)
    assert isinstance(result.scrubbed_trace, AgentTrace)


def test_scrub_result_to_dict(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(action="contact user@test.org")
    result = scrubber.scrub(trace)
    d = result.to_dict()
    assert "original_trace_id" in d
    assert "scrubbed_trace" in d
    assert "replacements_count" in d
    assert "patterns_matched" in d


def test_scrub_credit_card(scrubber: PrivacyScrubber) -> None:
    trace = _make_trace(observation="Charge 5500 0000 0000 0004 for order")
    result = scrubber.scrub(trace)
    assert result.replacements_count >= 1
    assert "credit_card" in result.patterns_matched


def test_scrub_rebuilds_hash_chain(scrubber: PrivacyScrubber) -> None:
    """After scrubbing, the resulting trace should have a valid chain."""
    steps = [
        TraceStep(0, "user@a.com called", "logged", "success"),
        TraceStep(1, "processed result", "done", "success"),
    ]
    trace = AgentTrace("t", "agent", "task", steps, created_at=0.0)
    result = scrubber.scrub(trace)
    scrubbed = result.scrubbed_trace
    # Check chain is valid
    assert scrubbed.steps[0].parent_id is None
    assert scrubbed.steps[1].parent_id == scrubbed.steps[0].id
