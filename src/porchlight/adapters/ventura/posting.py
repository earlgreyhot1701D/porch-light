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
exactly the kind of fabricated fact this product refuses.

The same refusal applies to a city TYPO (§40c): when the stated weekday and the
stated date disagree ("Wednesday, August 13, 2026" — but Aug 13 is a Thursday),
the record is AMBIGUOUS. We do NOT pick a side to feed the posting-time
distribution — a distribution built on a guessed resolution of a city typo is a
fabricated input to a real decision. Ambiguous records are parsed, flagged, and
EXCLUDED from the distribution (their count reported alongside it). The date is
still exposed for lead-time / ordering, since the Brown Act requires the date, but
marked so a reader knows. Trusting a single signal is what this design keeps
refusing to do.

The parse runs over STORED text only, never re-fetching the corpus (§40b: a
152-document re-fetch would trip Ventura's rate limit and look like an attack).
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
    caller records it as unparsed and moves on, never a guessed time.

    `ambiguous` True means the statement parsed but its stated weekday and stated
    date DISAGREE (e.g. "Wednesday, August 13, 2026" — but Aug 13 is a Thursday).
    We do NOT pick a side: resolving a city typo to feed the posting-time
    distribution would be a fabricated input to a real decision (the schedule
    narrowing, §35g), the same class of error as guessing a posting time. So an
    ambiguous record is EXCLUDED from the distribution (`usable_for_distribution`
    is False) and its count is reported. The date is still exposed for lead-time /
    ordering — the Brown Act requires the DATE — but flagged so a reader knows.

    `weekday_matches` is None when there was nothing to compare (unparsed), else
    whether the stated weekday agrees with the computed date.
    """

    parsed: bool
    posted_at: datetime | None = None
    stated_weekday: str = ""
    weekday_matches: bool | None = None
    ambiguous: bool = False
    raw: str = ""

    @classmethod
    def unparsed(cls) -> "PostingStatement":
        return cls(parsed=False)

    @property
    def usable_for_distribution(self) -> bool:
        """True only for a clean parse whose weekday and date agree.

        The posting-time distribution (task 11.2) includes ONLY these. Ambiguous
        and unparsed records are counted and reported, never guessed into the data.
        """
        return self.parsed and not self.ambiguous


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

        # Stated weekday vs stated date disagree -> AMBIGUOUS. We do not resolve the
        # city's typo (six-days reasoning suggests the DATE is the likelier error,
        # but "likelier" is still a guess). Parse it, flag it, exclude it from the
        # distribution. The date remains available for lead-time/ordering, flagged.
        ambiguous = not weekday_matches

        return PostingStatement(
            parsed=True,
            posted_at=posted_at,
            stated_weekday=stated_weekday,
            weekday_matches=weekday_matches,
            ambiguous=ambiguous,
            raw=m.group(0),
        )
    except Exception:
        # Never raise from a source-text parser; an odd input is UNPARSED, not a crash.
        return PostingStatement.unparsed()
