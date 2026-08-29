"""Porch Light — five-layer retry budget (Spec 2 R5, §16a).

All decisions here are CODE. No model is consulted, and there is no silent model
fallback anywhere (§20f, never.md #7). The transient/permanent classifier is an
invisible-failure surface (a wrong classification either burns money retrying a
dead document forever, or gives up on a document that would have succeeded), so it
gets a property test.

Layers:
  L1  attempts per document per stage = 2 (attempt + one retry), then park.
  L2  classify(failure) -> transient (auto-retry next run) | permanent (never).
  L3  run circuit breaker: stop a run if > T4% of its documents fail.
  L4  consecutive-run quarantine: quarantine a body after T5 failed runs.
  L5  spend ceiling (ledger.py).
"""

from __future__ import annotations

from enum import Enum

from porchlight.pipeline.thresholds import (
    ATTEMPTS_PER_DOCUMENT,
    T4_CIRCUIT_BREAKER_PCT,
    T5_QUARANTINE_RUNS,
)


class FailureKind(str, Enum):
    TRANSIENT = "transient"   # parked, auto-retried next run
    PERMANENT = "permanent"   # parked, never auto-retried


# Permanent failure signals: these will fail identically on retry, so retrying
# hourly only burns money (§16a L2). Matched on a normalized reason string.
_PERMANENT_MARKERS = (
    "no_text_layer",       # image-only scan; nothing to extract without OCR (a human path)
    "image_only",
    "schema_failed_twice", # the rewrite verifier rejected output twice (Spec 3)
    "malformed_pdf",       # the file will not parse
    "unsupported_content",
)

# Transient failure signals: worth another try next run (§16a L2).
_TRANSIENT_MARKERS = (
    "timeout",
    "http_5",              # city 5xx
    "429",                 # rate limited
    "connection",
    "dependency_unavailable",
)


def classify_failure(reason: str) -> FailureKind:
    """Classify a failure reason as transient or permanent.

    Total function: any input returns a FailureKind. **Unknown reasons default to
    TRANSIENT** — the safe direction, because a false "permanent" silently drops a
    document that would have succeeded (a missed deadline), while a false
    "transient" costs only one more cheap retry next run. This matches the product's
    error asymmetry (§3).
    """
    r = (reason or "").lower()
    if any(m in r for m in _PERMANENT_MARKERS):
        return FailureKind.PERMANENT
    # Everything else, including unrecognized reasons, is transient.
    return FailureKind.TRANSIENT


def should_retry_now(attempts: int) -> bool:
    """L1: within-run retry budget. True iff another attempt is allowed this run."""
    return attempts < ATTEMPTS_PER_DOCUMENT


def circuit_broken(failed: int, attempted: int) -> bool:
    """L3: stop the run if more than T4% of attempted documents failed.

    attempted==0 is never broken (nothing tried yet).
    """
    if attempted <= 0:
        return False
    return (failed / attempted) * 100 > T4_CIRCUIT_BREAKER_PCT


def should_quarantine(consecutive_failed_runs: int) -> bool:
    """L4: quarantine a body after T5 consecutive failed runs (§16a)."""
    return consecutive_failed_runs >= T5_QUARANTINE_RUNS
