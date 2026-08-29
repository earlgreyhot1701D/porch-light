"""Property + example tests for the Ventura horizon and surfacing rules.

# Feature: 1-ventura-adapter, Property 2: horizon and surfacing

Invisible-failure surface: a wrong horizon silently drops a real meeting; a wrong
surfacing decision silently shows a past meeting as upcoming or hides an imminent
one. The DST cases are explicit because time is the highest-harm field (§2), and
the day-of-meeting boundary is where day-granularity would bite hardest (§35).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given, strategies as st

from porchlight.adapters.ventura.horizon import (
    CITY_TZ,
    HORIZON_FUTURE_DAYS,
    HORIZON_PAST_DAYS,
    in_horizon,
    is_upcoming,
)
from porchlight.adapters.ventura.models import Meeting, MeetingType


def _meeting(mdate: date, start: datetime | None) -> Meeting:
    return Meeting(
        meeting_id="t",
        body_id="city_council",
        meeting_date=mdate,
        meeting_type=MeetingType.REGULAR,
        start_time_local=start,
        documents=(),
    )


# --- in_horizon example + property ---

def test_in_horizon_edges():
    today = date(2026, 8, 27)
    assert in_horizon(today, today)
    assert in_horizon(today + timedelta(days=HORIZON_FUTURE_DAYS), today)
    assert in_horizon(today - timedelta(days=HORIZON_PAST_DAYS), today)
    assert not in_horizon(today + timedelta(days=HORIZON_FUTURE_DAYS + 1), today)
    assert not in_horizon(today - timedelta(days=HORIZON_PAST_DAYS + 1), today)


@given(offset=st.integers(min_value=-400, max_value=400))
def test_in_horizon_matches_window(offset):
    """Property: in_horizon is true exactly within [-T2, +T1] days of today."""
    today = date(2026, 8, 27)
    md = today + timedelta(days=offset)
    expected = -HORIZON_PAST_DAYS <= offset <= HORIZON_FUTURE_DAYS
    assert in_horizon(md, today) == expected


# --- The core §35 correction: 5:00 PM boundary, both DST directions ---

def test_five_pm_boundary_spring_forward():
    """Spring-forward 2026: DST begins Sun Mar 8 2026. Use a meeting that day at 5 PM."""
    mdate = date(2026, 3, 8)
    start = datetime(2026, 3, 8, 17, 0, tzinfo=CITY_TZ)
    m = _meeting(mdate, start)
    at_459 = datetime(2026, 3, 8, 16, 59, tzinfo=CITY_TZ)
    at_501 = datetime(2026, 3, 8, 17, 1, tzinfo=CITY_TZ)
    assert is_upcoming(m, at_459) is True
    assert is_upcoming(m, at_501) is False


def test_five_pm_boundary_fall_back():
    """Fall-back 2026: DST ends Sun Nov 1 2026. Use a meeting that day at 5 PM."""
    mdate = date(2026, 11, 1)
    start = datetime(2026, 11, 1, 17, 0, tzinfo=CITY_TZ)
    m = _meeting(mdate, start)
    at_459 = datetime(2026, 11, 1, 16, 59, tzinfo=CITY_TZ)
    at_501 = datetime(2026, 11, 1, 17, 1, tzinfo=CITY_TZ)
    assert is_upcoming(m, at_459) is True
    assert is_upcoming(m, at_501) is False


def test_boundary_holds_when_now_is_in_utc():
    """A runner clock in UTC must not change the city-local decision."""
    start = datetime(2026, 6, 10, 17, 0, tzinfo=CITY_TZ)
    m = _meeting(date(2026, 6, 10), start)
    # 16:59 PDT == 23:59 UTC; 17:01 PDT == 00:01 UTC next day.
    utc = ZoneInfo("UTC")
    assert is_upcoming(m, datetime(2026, 6, 11, 0, 0, tzinfo=utc)) is False  # after 17:00 PDT
    assert is_upcoming(m, datetime(2026, 6, 10, 23, 0, tzinfo=utc)) is True   # 16:00 PDT


def test_unknown_time_falls_back_to_end_of_day():
    """No parsed time -> upcoming until end of the meeting day (errs toward showing)."""
    m = _meeting(date(2026, 6, 10), None)
    before_midnight = datetime(2026, 6, 10, 23, 0, tzinfo=CITY_TZ)
    next_day = datetime(2026, 6, 11, 0, 1, tzinfo=CITY_TZ)
    assert is_upcoming(m, before_midnight) is True
    assert is_upcoming(m, next_day) is False


@given(hour=st.integers(min_value=0, max_value=23), minute=st.integers(min_value=0, max_value=59))
def test_upcoming_monotonic_around_start(hour, minute):
    """Property: for a known start time, is_upcoming is True strictly before start
    and False at/after start, on the same day."""
    start = datetime(2026, 6, 10, 17, 0, tzinfo=CITY_TZ)
    m = _meeting(date(2026, 6, 10), start)
    now = datetime(2026, 6, 10, hour, minute, tzinfo=CITY_TZ)
    assert is_upcoming(m, now) == (now < start)
