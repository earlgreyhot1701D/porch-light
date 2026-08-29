"""Retry-budget tests (Spec 2 task 5.2).

# Feature: 2-ingestion, Property 2: retry classification

The transient/permanent classifier is an invisible-failure surface: a wrong
"permanent" silently drops a document that would have succeeded (a missed
deadline); a wrong "transient" costs one cheap retry. Pure functions, no DB.
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from porchlight.pipeline.retry import (
    FailureKind,
    circuit_broken,
    classify_failure,
    should_quarantine,
    should_retry_now,
)
from porchlight.pipeline.thresholds import (
    ATTEMPTS_PER_DOCUMENT,
    T4_CIRCUIT_BREAKER_PCT,
    T5_QUARANTINE_RUNS,
)


# --- classify_failure: examples on real reason strings ---

def test_permanent_examples():
    for r in ["no_text_layer", "image_only scan", "schema_failed_twice", "malformed_pdf"]:
        assert classify_failure(r) == FailureKind.PERMANENT


def test_transient_examples():
    for r in ["timeout", "http_503", "429 too many", "connection reset", "dependency_unavailable"]:
        assert classify_failure(r) == FailureKind.TRANSIENT


def test_unknown_reason_defaults_transient():
    # The safe direction: unknown → transient (retry cheaply) not permanent (drop).
    assert classify_failure("something we have never seen") == FailureKind.TRANSIENT
    assert classify_failure("") == FailureKind.TRANSIENT


@given(reason=st.text(max_size=200))
def test_classify_is_total(reason):
    """Property: any input returns a FailureKind, never raises."""
    assert isinstance(classify_failure(reason), FailureKind)


@given(reason=st.text(max_size=200))
def test_no_permanent_without_a_permanent_marker(reason):
    """Property: PERMANENT is only ever returned when a permanent marker is present.
    A document is never silently dropped on an unrecognized reason."""
    markers = ("no_text_layer", "image_only", "schema_failed_twice", "malformed_pdf", "unsupported_content")
    if classify_failure(reason) == FailureKind.PERMANENT:
        assert any(m in reason.lower() for m in markers)


# --- L1 attempts ---

def test_should_retry_within_budget():
    assert should_retry_now(0) is True
    assert should_retry_now(ATTEMPTS_PER_DOCUMENT - 1) is True
    assert should_retry_now(ATTEMPTS_PER_DOCUMENT) is False


# --- L3 circuit breaker ---

def test_circuit_breaker():
    assert circuit_broken(0, 0) is False          # nothing attempted
    assert circuit_broken(0, 10) is False
    # Just over T4%
    over = int(10 * (T4_CIRCUIT_BREAKER_PCT / 100)) + 1
    assert circuit_broken(over, 10) is True
    # Exactly at T4% is not "more than", so not broken.
    at = 10 * T4_CIRCUIT_BREAKER_PCT // 100
    assert circuit_broken(at, 10) is False


# --- L4 quarantine ---

def test_quarantine_threshold():
    assert should_quarantine(T5_QUARANTINE_RUNS - 1) is False
    assert should_quarantine(T5_QUARANTINE_RUNS) is True
