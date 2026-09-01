"""Tests for the watcher's contract types (Spec 5 task 2.2, R1.1/R6.2/never.md #10)."""
from __future__ import annotations

import dataclasses

from porchlight.watch.models import BilingualReason, WatchAnswer, WatchMatch


def test_match_cannot_be_constructed_without_a_reason():
    # never.md #10: reason is required — no default, no setter. A match with no
    # reason is not constructable.
    import pytest

    with pytest.raises(TypeError):
        WatchMatch(item_id="3685-6")  # type: ignore[call-arg]

    m = WatchMatch(item_id="3685-6", reason=BilingualReason(en="why", es="por que"))
    assert m.reason.en and m.reason.es


def test_match_type_has_no_receipt_field_a_model_could_fill():
    # never.md #6: the model has nothing to author a receipt into. Assert the type
    # carries no receipt/deadline/body/page/url field.
    fields = {f.name for f in dataclasses.fields(WatchMatch)}
    forbidden = {
        "body", "meeting_date", "item_number", "page_range", "page_start",
        "page_end", "deadline", "source_url", "url", "receipt",
    }
    assert fields.isdisjoint(forbidden), f"WatchMatch must not carry receipt fields: {fields & forbidden}"


def test_match_and_answer_are_frozen():
    m = WatchMatch(item_id="x", reason=BilingualReason(en="a", es="b"))
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        m.item_id = "y"  # type: ignore[misc]


def test_quiet_vs_partial_vs_degraded_are_distinct():
    quiet = WatchAnswer()
    assert quiet.is_quiet and not quiet.degraded and not quiet.is_partial

    degraded = WatchAnswer(degraded=True, note="model unavailable")
    assert not degraded.is_quiet and degraded.degraded

    partial = WatchAnswer(
        matches=(WatchMatch(item_id="x", reason=BilingualReason(en="a", es="b")),),
        is_partial=True,
    )
    assert not partial.is_quiet and partial.is_partial and partial.matches
