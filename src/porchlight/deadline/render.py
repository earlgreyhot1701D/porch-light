"""Deadline rendering — city local time, always labeled (R7, §2, voice.md).

Pure functions, no I/O, no model. The deadline VALUE is copied from source
upstream (never.md #1: dates/deadlines are never model-generated); this module
only formats an already-known instant for display.

Two rules this module exists to enforce, both of which are how a watcher misses a
deadline if we get them wrong:

  1. Render in CITY local time (America/Los_Angeles), ALWAYS labeled with the
     zone, never silently converted to the viewer's zone. A watcher may be
     traveling or on a phone set to UTC. The label format is fixed by voice.md:
         "5:00 PM · Pacific, city local time"
  2. Relative phrasing ("closes tomorrow at 5" / "cierra manana a las 5") is
     computed against CITY time, not the server's or viewer's clock, so "tomorrow"
     means tomorrow in Ventura. This is the case the DST-boundary test pins: a
     naive UTC subtraction gives the wrong day across a spring-forward.

Bilingual by construction (voice.md): every user-facing string exists in English
and Spanish with equal weight. Relative phrases are gender-neutral in both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

CITY_TZ = ZoneInfo("America/Los_Angeles")
"""Ventura's zone. Deadlines render here regardless of where the viewer is."""

# voice.md fixes this exact label. PST/PDT both render as "Pacific" — the point is
# the city's clock, labeled, not the abbreviation of the moment.
_ZONE_LABEL = "Pacific, city local time"


class Language(str, Enum):
    EN = "en"
    ES = "es"


@dataclass(frozen=True)
class RenderedDeadline:
    """A deadline formatted for one language.

    `absolute` is the always-shown, always-labeled city-local time. `relative` is
    the computed-against-city-time phrase ("closes tomorrow at 5"). Both are shown;
    the relative phrase never replaces the labeled absolute one.
    """

    language: Language
    absolute: str
    relative: str


def _to_city(dt: datetime) -> datetime:
    """Move a tz-aware instant into city local time. Naive input is rejected."""
    if dt.tzinfo is None:
        raise ValueError("deadline datetime must be timezone-aware")
    return dt.astimezone(CITY_TZ)


def _format_time(city_dt: datetime) -> str:
    """'5:00 PM' — no leading zero on the hour, matching voice.md's example."""
    hour = city_dt.hour % 12 or 12
    ampm = "AM" if city_dt.hour < 12 else "PM"
    return f"{hour}:{city_dt.minute:02d} {ampm}"


def format_absolute(deadline: datetime, language: Language) -> str:
    """The always-shown labeled city-local time, e.g. '5:00 PM · Pacific, city local time'.

    The zone label is identical in both languages (it names Ventura's clock, a
    proper reference, not a translatable phrase) except the connective wording.
    """
    city_dt = _to_city(deadline)
    time_str = _format_time(city_dt)
    if language is Language.ES:
        return f"{time_str} · Pacifico, hora local de la ciudad"
    return f"{time_str} · {_ZONE_LABEL}"


def format_relative(deadline: datetime, now: datetime, language: Language) -> str:
    """Relative phrasing computed against CITY time (R7.2).

    Args:
        deadline: tz-aware deadline instant (copied from source upstream).
        now: tz-aware current instant (any zone; converted to city time here).
        language: EN or ES.

    Returns:
        A calm, gender-neutral phrase. Day difference is computed on CITY calendar
        dates, so "tomorrow" is tomorrow in Ventura even across a DST boundary.
        Never scolds (voice.md): a past deadline reads "closed", not "missed".
    """
    city_deadline = _to_city(deadline)
    city_now = _to_city(now)
    day_delta = (city_deadline.date() - city_now.date()).days
    time_str = _format_time(city_deadline)

    if language is Language.ES:
        if day_delta < 0:
            return "cerrado"
        if day_delta == 0:
            return f"cierra hoy a las {time_str}"
        if day_delta == 1:
            return f"cierra manana a las {time_str}"
        return f"cierra en {day_delta} dias, a las {time_str}"

    if day_delta < 0:
        return "closed"
    if day_delta == 0:
        return f"closes today at {time_str}"
    if day_delta == 1:
        return f"closes tomorrow at {time_str}"
    return f"closes in {day_delta} days, at {time_str}"


def render(deadline: datetime, now: datetime, language: Language) -> RenderedDeadline:
    """Render a deadline for one language: labeled absolute + city-relative phrase."""
    return RenderedDeadline(
        language=language,
        absolute=format_absolute(deadline, language),
        relative=format_relative(deadline, now, language),
    )
