"""Property + example tests for the Brown Act posting-statement parser.

# Feature: 1-ventura-adapter, Property 4: posting statement

The parser is an invisible-failure surface: a guessed posting time would feed a
schedule-narrowing decision (§35g) with a fabricated fact, and a silently-wrong
one is worse than none. So the property under test is HONEST FAILURE — when the
wording varies from the known Brown Act pattern, the parser returns UNPARSED, it
never invents a time.

Example tests pin the two verbatim samples verified against real Ventura agendas
(§40).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from hypothesis import given, strategies as st

from porchlight.adapters.ventura.posting import (
    CITY_TZ,
    PostingStatement,
    parse_posting_statement,
)

# The two verified samples (§40).
_AUG18 = (
    "This agenda was posted on Wednesday, August 13, 2026, at 5:00 p.m. in the "
    "City Clerk's Office, on the City Hall Public Notices Board and on the internet."
)
_AUG25 = (
    "This agenda was posted on Wednesday, August 19, 2026, at 5:00 p.m. in the "
    "City Clerk's Office, on the City Hall Public Notices Board and on the internet."
)


def test_aug18_sample_is_ambiguous_and_excluded_from_distribution():
    # The Aug 18 agenda's posting statement says "Wednesday, August 13, 2026" — but
    # Aug 13, 2026 is a THURSDAY. Weekday and date disagree. We do NOT resolve the
    # typo (six-days reasoning suggests the date is the likelier error, but that is
    # still a guess). The record is AMBIGUOUS: parsed, flagged, and excluded from
    # the posting-time distribution (§40c). The date stays available, flagged.
    r = parse_posting_statement(_AUG18)
    assert r.parsed
    assert r.ambiguous is True
    assert r.weekday_matches is False
    assert r.usable_for_distribution is False
    # Date still exposed for lead-time/ordering (Brown Act requires the date).
    assert r.posted_at == datetime(2026, 8, 13, 17, 0, tzinfo=CITY_TZ)


def test_parses_aug25_sample_clean_and_usable():
    # Aug 19, 2026 genuinely is a Wednesday, so this one's weekday agrees: usable.
    r = parse_posting_statement(_AUG25)
    assert r.parsed
    assert r.ambiguous is False
    assert r.weekday_matches is True
    assert r.usable_for_distribution is True
    assert r.posted_at == datetime(2026, 8, 19, 17, 0, tzinfo=CITY_TZ)


def test_both_samples_posted_at_5pm():
    # The §40 observation the schedule narrowing rests on: both posted at 5:00 p.m.
    # (The Aug 18 weekday/date conflict is a separate, flagged issue.)
    for text in (_AUG18, _AUG25):
        r = parse_posting_statement(text)
        assert (r.posted_at.hour, r.posted_at.minute) == (17, 0)


def test_clean_record_is_usable_ambiguous_is_not():
    clean = parse_posting_statement("posted on Wednesday, August 19, 2026, at 5:00 p.m. ...")
    ambiguous = parse_posting_statement("posted on Wednesday, August 13, 2026, at 5:00 p.m. ...")
    unparsed = parse_posting_statement("no posting statement here")
    assert clean.usable_for_distribution is True
    assert ambiguous.usable_for_distribution is False  # parsed but conflicted
    assert ambiguous.parsed is True
    assert unparsed.usable_for_distribution is False  # not parsed at all
    assert unparsed.parsed is False


def test_noon_and_midnight_boundaries():
    noon = parse_posting_statement("posted on Monday, June 1, 2026, at 12:00 p.m. ...")
    assert noon.posted_at == datetime(2026, 6, 1, 12, 0, tzinfo=CITY_TZ)
    midnight = parse_posting_statement("posted on Monday, June 1, 2026, at 12:00 a.m. ...")
    assert midnight.posted_at == datetime(2026, 6, 1, 0, 0, tzinfo=CITY_TZ)


def test_weekday_mismatch_is_ambiguous_not_failed():
    # Aug 13, 2026 is a Thursday; the doc says Tuesday. Parse succeeds (date usable
    # for ordering) but the record is ambiguous and excluded from the distribution.
    r = parse_posting_statement("posted on Tuesday, August 13, 2026, at 5:00 p.m. ...")
    assert r.parsed
    assert r.weekday_matches is False
    assert r.ambiguous is True
    assert r.usable_for_distribution is False


# --- Honest failure: varied wording never guesses ---

def test_absent_statement_is_unparsed():
    assert parse_posting_statement("An ordinary agenda item with no posting line.").parsed is False


def test_varied_wording_is_unparsed():
    # Real risk: a reworded statement must not be force-fit into a guessed time.
    varied = "This agenda became available to the public last Wednesday afternoon."
    assert parse_posting_statement(varied).parsed is False


def test_empty_and_none_are_unparsed():
    assert parse_posting_statement("").parsed is False
    assert parse_posting_statement(None).parsed is False  # type: ignore[arg-type]


# --- Property tests ---

@given(st.text(max_size=400))
def test_property_never_raises_and_unparsed_carries_no_time(text: str):
    """On any input the parser returns a PostingStatement; UNPARSED carries no time."""
    r = parse_posting_statement(text)
    assert isinstance(r, PostingStatement)
    if not r.parsed:
        assert r.posted_at is None


@given(
    month=st.sampled_from(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]
    ),
    day=st.integers(min_value=1, max_value=28),
    year=st.integers(min_value=2024, max_value=2030),
    hour=st.integers(min_value=1, max_value=12),
    minute=st.integers(min_value=0, max_value=59),
    ampm=st.sampled_from(["a.m.", "p.m."]),
)
def test_property_well_formed_statement_round_trips(month, day, year, hour, minute, ampm):
    """A well-formed Brown Act statement always parses to a matching city-local instant."""
    text = f"This agenda was posted on Monday, {month} {day}, {year}, at {hour}:{minute:02d} {ampm} in the City Clerk's Office."
    r = parse_posting_statement(text)
    assert r.parsed
    assert r.posted_at is not None
    expected_hour = hour % 12 + (12 if ampm == "p.m." else 0)
    assert r.posted_at.hour == expected_hour
    assert r.posted_at.minute == minute
    assert r.posted_at.tzinfo is CITY_TZ or str(r.posted_at.tzinfo) == str(CITY_TZ)
