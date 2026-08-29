"""Ventura adapter — ingestion horizon and surfacing rule (R4, R5).

Pure functions. The two invisible-failure surfaces this file owns are exactly
where the property tests live (rigor budget): a wrong horizon silently drops a
real meeting, and a wrong surfacing decision silently shows a past meeting as
upcoming or hides an imminent one.

Time is the highest-harm field in the system (§2). All comparisons are in city
local time (America/Los_Angeles), never the server clock or the viewer's zone,
and never silently converted.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from porchlight.adapters.ventura.models import Meeting

CITY_TZ = ZoneInfo("America/Los_Angeles")

# Thresholds T1/T2 (requirements R8). Values are the proposed Spec 1 numbers;
# finalized at Spec 2 close. Each is here with its rationale rather than inline.
HORIZON_FUTURE_DAYS = 30  # T1: realistic scheduling lead time with margin.
HORIZON_PAST_DAYS = 14    # T2: catches an agenda amended shortly after its meeting.


def now_city_local() -> datetime:
    """Current time in city local zone. Wrapped so tests can compare against it."""
    return datetime.now(CITY_TZ)


def today_city_local() -> date:
    """Current date in city local zone."""
    return now_city_local().date()


def in_horizon(meeting_date: date, today: date | None = None) -> bool:
    """True iff the meeting date is within the ingestion window (R4).

    Window is [today - T2, today + T1], computed from the MEETING date — never
    the posting date, never the file name (R4.1). Enforced before any per-meeting
    fetch (R4.3), so out-of-window meetings cost zero fetches.
    """
    if today is None:
        today = today_city_local()
    earliest = today - timedelta(days=HORIZON_PAST_DAYS)
    latest = today + timedelta(days=HORIZON_FUTURE_DAYS)
    return earliest <= meeting_date <= latest


def _meeting_start(meeting: Meeting) -> datetime:
    """Resolve the meeting's start datetime in city local time.

    Uses the parsed start time when known. Falls back to END OF DAY city-local
    when the time is unknown, and the CALLER logs that fallback (R5.4) — a
    day-granularity decision must never be made silently.

    The fallback is end-of-day (not start-of-day) deliberately: if we do not know
    the time, treating the meeting as "still upcoming until the day ends" errs
    toward showing it, which matches the product's error asymmetry (a false
    "upcoming" is mild; a false "already happened" could hide a deadline).
    """
    if meeting.start_time_local is not None:
        dt = meeting.start_time_local
        # Ensure it is city-local and tz-aware.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=CITY_TZ)
        return dt.astimezone(CITY_TZ)
    # Fallback: end of the meeting day, city local.
    return datetime.combine(meeting.meeting_date, time(23, 59, 59), tzinfo=CITY_TZ)


def meeting_time_is_known(meeting: Meeting) -> bool:
    """Whether the meeting start time was parsed. Caller logs the fallback if not."""
    return meeting.start_time_local is not None


def is_upcoming(meeting: Meeting, now: datetime | None = None) -> bool:
    """True iff the meeting has not yet started, in city local time (R5).

    Compares against the meeting START datetime, not the date: a 5:00 PM meeting
    stops being upcoming at 5:00 PM, not at midnight. The product's whole job is
    notifying BEFORE a meeting starts, so day granularity on the day-of is a bug
    (§35 correction), not an acceptable approximation.

    Independent of posting/ingestion: an agenda amended after a past meeting is
    ingested (if in horizon) but is never upcoming (R5.2).

    Callers SHOULD check `meeting_time_is_known(meeting)` and log when it is False
    (R5.4), because the end-of-day fallback is a weaker guarantee.
    """
    if now is None:
        now = now_city_local()
    if now.tzinfo is None:
        now = now.replace(tzinfo=CITY_TZ)
    return _meeting_start(meeting) > now.astimezone(CITY_TZ)
