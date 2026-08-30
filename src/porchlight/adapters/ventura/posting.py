"""Ventura adapter — the Brown Act posting-statement parser (R2, §40).

Pure function, no I/O, no model (§model-authority: this is source text, parsed
deterministically). Every Ventura agenda carries a legally-required posting
statement declaring when the CITY posted it — date AND time — in the document
text. Two verified samples, both Wednesday at 5:00 p.m.:

    "This agenda was posted on Wednesday, August 13, 2026, at 5:00 p.m. in the
     City Clerk's Office, on the City Hall Public Notices Board and on the
     internet."

    "This agenda was posted on Wednesday, August 19, 2026, at 5:00 p.m. ..."

This is the CITY's declaration of when it posted, not our observation of when we
noticed — better than run-log first-seen three ways (§40): retroactive across the
152 agendas already stored, the city's own statement rather than our detection
latency, and legally mandated so it will not quietly vanish. The posting-time
distribution (task 11.2) is built from THIS, with run-log first-seen kept as a
cross-check (a gap between declared and observed is itself worth knowing).

Honest failure is a requirement, not a nicety (§40, never.md #1): when the wording
varies from the known pattern, the parser returns UNPARSED — it never guesses a
posting time. A guessed posting time feeding a schedule-narrowing decision is
exactly the kind of fabricated fact this product refuses. The parse runs over
STORED text only, never re-fetching the corpus (§40b: a 152-document re-fetch
would trip Ventura's rate limit and look like an attack).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

CITY_TZ = ZoneInfo("America/Los_Angeles")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_MONTH_ALT = "|".join(_MONTHS)

# The Brown Act posting statement. Anchored on "posted on <weekday>, <Month> <day>,
# <year>, at <h>:<mm> <a.m./p.m.>". The weekday is captured but NOT trusted for the
# date (we compute the date from month/day/year); a mismatch between the stated
# weekday and the computed one is surfaced as a data-quality signal, not silently
# corrected. Whitespace is tolerant; the wording is otherwise consistent.
_POSTING = re.compile(
    r"posted\s+on\s+"
    r"(?P<weekday>[A-Za-z]+),\s*"
    rf"(?P<month>{_MONTH_ALT})\s+(?P<day>\d{{1,2}}),\s*(?P<year>\d{{4}})"
    r"\s*,?\s*at\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>a\.?m\.?|p\.?m\.?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PostingStatement:
    """A parsed posting statement, or an honest UNPARSED outcome.

    `posted_at` is the city-local, tz-aware posting instant when parsed, else None.
    `parsed` False means the statement was absent or worded differently — the
    caller records it as unparsed and moves on, never a guessed time. `stated_weekday`
    is what the document said; `weekday_matches` is whether it agrees with the
    computed date (a False here is a data-quality flag worth logging, not a parse
    failure).
    """

    parsed: bool
    posted_at: datetime | None = None
    stated_weekday: str = ""
    weekday_matches: bool | None = None
    raw: str = ""

    @classmethod
    def unparsed(cls) -> "PostingStatement":
        return cls(parsed=False)


def parse_posting_statement(document_text: str) -> PostingStatement:
    """Parse the Brown Act posting statement from an agenda's stored text (§40).

    Args:
        document_text: the agenda's stored text (never re-fetched, §40b).

    Returns:
        A PostingStatement. UNPARSED when the statement is absent or the wording
        varies — never a guessed time (honest failure, §40). Never raises: any
        unexpected input degrades to UNPARSED.
    """
    try:
        text = document_text or ""
        m = _POSTING.search(text)
        if not m:
            return PostingStatement.unparsed()

        month = _MONTHS[m.group("month").lower()]
        day = int(m.group("day"))
        year = int(m.group("year"))
        hour = int(m.group("hour"))
        minute = int(m.group("minute"))
        is_pm = m.group("ampm").lower().startswith("p")

        # 12-hour to 24-hour. 12:xx p.m. is noon; 12:xx a.m. is midnight.
        if hour == 12:
            hour = 12 if is_pm else 0
        elif is_pm:
            hour += 12

        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 1 <= day <= 31):
            return PostingStatement.unparsed()

        posted_at = datetime(year, month, day, hour, minute, tzinfo=CITY_TZ)

        stated_weekday = m.group("weekday")
        # Python weekday(): Monday=0 .. Sunday=6.
        _WD = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        weekday_matches = _WD[posted_at.weekday()] == stated_weekday.lower()

        return PostingStatement(
            parsed=True,
            posted_at=posted_at,
            stated_weekday=stated_weekday,
            weekday_matches=weekday_matches,
            raw=m.group(0),
        )
    except Exception:
        # Never raise from a source-text parser; an odd input is UNPARSED, not a crash.
        return PostingStatement.unparsed()
