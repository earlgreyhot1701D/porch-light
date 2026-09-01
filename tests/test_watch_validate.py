"""Tests for watch-input validation (Spec 5 task 1.2, R3.5/R4.2/R4.3)."""
from __future__ import annotations

from porchlight.watch.validate import MAX_TERM_CHARS, MAX_TERMS, validate_watchlist


def test_at_cap_passes():
    terms = [f"term {i}" for i in range(MAX_TERMS)]  # exactly 10
    r = validate_watchlist(terms)
    assert r.ok
    assert len(r.terms) == MAX_TERMS


def test_over_term_count_rejects_with_reason():
    r = validate_watchlist([f"t{i}" for i in range(MAX_TERMS + 1)])
    assert not r.ok
    assert r.rejections
    assert "too many terms" in r.rejections[0][1]


def test_term_at_char_cap_passes_over_cap_rejects():
    at_cap = "x" * MAX_TERM_CHARS
    over = "x" * (MAX_TERM_CHARS + 1)
    assert validate_watchlist([at_cap]).ok
    r = validate_watchlist([over])
    assert not r.ok
    assert "too long" in r.rejections[0][1]


def test_control_chars_rejected():
    r = validate_watchlist(["short-term rentals\n"])  # trailing newline is a control char
    # trailing newline is stripped by .strip(); use an interior control char.
    r2 = validate_watchlist(["short\x00term"])
    assert not r2.ok
    assert "control characters" in r2.rejections[0][1]
    # A term that is ONLY whitespace/newline is dropped as blank, list stays ok+empty.
    assert validate_watchlist(["\n\t "]).ok


def test_blanks_dropped_not_rejected():
    r = validate_watchlist(["the pier", "", "   ", "short-term rentals"])
    assert r.ok
    assert r.terms == ("the pier", "short-term rentals")


def test_duplicates_collapse_case_insensitive():
    r = validate_watchlist(["The Pier", "the pier", "THE PIER"])
    assert r.ok
    assert r.terms == ("The Pier",)


def test_non_string_term_rejected():
    r = validate_watchlist(["ok term", 42])  # type: ignore[list-item]
    assert not r.ok
    assert any("must be text" in reason for _, reason in r.rejections)


def test_shared_link_terms_take_the_same_path():
    # R4.3: incoming shared-link terms are validated exactly like typed terms.
    incoming = ["parking", "x" * (MAX_TERM_CHARS + 5)]
    r = validate_watchlist(incoming)
    assert not r.ok  # the over-long shared term is caught by the same rule
    assert any("too long" in reason for _, reason in r.rejections)


def test_non_list_input_rejected():
    r = validate_watchlist("parking")  # type: ignore[arg-type]
    assert not r.ok
