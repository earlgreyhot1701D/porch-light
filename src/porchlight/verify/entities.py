"""Entity extraction — pull candidate entities out of source or rewrite text.

Pure functions, no I/O, no model (§model-authority: entity handling is code).
This module only *finds* candidate entities as raw spans; `normalize.py` decides
which classes canonicalize and which compare raw. Keeping extraction and
normalization in separate modules is deliberate: extraction is a
recall-oriented net (find every plausible date/number/name), normalization is
the equivalence rule. A bug in one should not hide in the other.

Entity classes (design R3a table):
  - DATE      -> normalized to ISO 8601 (2026-02-10)
  - NUMBER    -> normalized to a numeric value + unit (currency, percent, plain)
  - NAME      -> compared RAW (proper nouns, person, street, body names): these
                 must NOT change in translation, so a translated street name is a
                 real failure the verifier must catch.

Bilingual by construction: date and number patterns match English and Spanish
surface forms (e.g. "February 10, 2026" and "10 de febrero de 2026";
"$1.2 million" and "$1.2 millones"). Names are language-agnostic spans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class EntityClass(str, Enum):
    """What kind of entity a span is, which decides how it is compared."""

    DATE = "date"
    NUMBER = "number"
    NAME = "name"


@dataclass(frozen=True)
class Entity:
    """One extracted candidate entity: its class and its raw source span."""

    entity_class: EntityClass
    raw: str
    """The verbatim text as it appeared, before any normalization."""


# --- Month names, English and Spanish, for date extraction. ---
_MONTHS_EN = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)
_MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_MONTH_ALT = "|".join(_MONTHS_EN + _MONTHS_ES)

# "February 10, 2026" / "February 10 2026"
_DATE_EN = re.compile(
    rf"\b(?:{_MONTH_ALT})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b",
    re.IGNORECASE,
)
# "10 de febrero de 2026" / "10 February 2026"
_DATE_ES = re.compile(
    rf"\b\d{{1,2}}\s+(?:de\s+)?(?:{_MONTH_ALT})\s+(?:de\s+)?\d{{4}}\b",
    re.IGNORECASE,
)
# Numeric: 02/10/2026, 2026-02-10, 02-10-2026
_DATE_NUMERIC = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b"
)

# --- Numbers: currency, percent, and magnitude words in both languages. ---
# "$1.2 million", "$1,200,000", "$1.2 millones", "1.2 million", "45%", "45 percent"
_MAGNITUDE = "million|millones|mil|billion|billones|thousand"
_NUMBER = re.compile(
    rf"""
    (?P<currency>\$)?\s*
    \d[\d,]*(?:\.\d+)?
    (?:\s*(?:{_MAGNITUDE}))?
    (?:\s*(?:%|percent|por\s+ciento))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A number span is only interesting if it carries a currency sign, a magnitude
# word, a percent marker, or is a bare multi-digit amount. A lone "10" inside a
# date is already consumed by the date pass, so date spans are removed first.
_INTERESTING_NUMBER = re.compile(
    rf"(\$)|({_MAGNITUDE})|(%|percent|por\s+ciento)|(\d[\d,]*\.\d+)|(\d{{2,}})",
    re.IGNORECASE,
)

# --- Names: capitalized multi-word proper nouns and street patterns.
# Recall-oriented; false positives are harmless because names compare raw and a
# name present in both source and output simply matches. ---
_STREET = re.compile(
    r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+"
    r"(?:Street|St\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Road|Rd\.?|Drive|Dr\.?|"
    r"Lane|Ln\.?|Way|Court|Ct\.?|Place|Pl\.?)\b"
)
_PROPER = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+\b")


def _find(pattern: re.Pattern[str], text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0).strip()) for m in pattern.finditer(text)]


def extract(text: str) -> list[Entity]:
    """Extract all candidate entities from a block of text.

    Args:
        text: source page-range text or a rewrite.

    Returns:
        Entities in class order (dates, then numbers, then names). Date spans are
        removed before number extraction so a day-of-month is not double-counted
        as a number. Order within a class is document order.

    Never raises: unexpected input yields an empty list.
    """
    try:
        text = text or ""
        entities: list[Entity] = []

        # 1. Dates first, and record their spans to mask from the number pass.
        date_spans: list[tuple[int, int]] = []
        for pat in (_DATE_EN, _DATE_ES, _DATE_NUMERIC):
            for start, end, raw in _find(pat, text):
                date_spans.append((start, end))
                entities.append(Entity(EntityClass.DATE, raw))

        def _overlaps_date(start: int, end: int) -> bool:
            # Overlap, not just start-position containment: the number regex's
            # leading \s* can push m.start() one char before a date span while the
            # digits themselves sit inside it (the "10 de febrero" case).
            return any(start < e and s < end for s, e in date_spans)

        # 2. Numbers, skipping anything overlapping a matched date span.
        for m in _NUMBER.finditer(text):
            raw = m.group(0).strip()
            if not raw or _overlaps_date(m.start(), m.end()):
                continue
            if _INTERESTING_NUMBER.search(raw):
                entities.append(Entity(EntityClass.NUMBER, raw))

        # 3. Names: streets first (more specific), then general proper nouns.
        seen_name_spans: list[tuple[int, int]] = []
        for start, end, raw in _find(_STREET, text):
            seen_name_spans.append((start, end))
            entities.append(Entity(EntityClass.NAME, raw))
        for m in _PROPER.finditer(text):
            if any(s <= m.start() < e for s, e in seen_name_spans):
                continue
            entities.append(Entity(EntityClass.NAME, m.group(0).strip()))

        return entities
    except Exception:
        return []
