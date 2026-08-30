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

from porchlight.log import get_logger

log = get_logger("porchlight.verify.entities")


# ---------------------------------------------------------------------------
# Artifact-tolerant extraction (VIEW ONLY) — the extractor reads THROUGH a repair
# pass; it NEVER writes back. source.text stays byte-for-byte with its mojibake,
# forever (calibration decision 3). The repair maps the known PDF-text-layer
# artifacts to their intended characters, and collapses a spurious intra-word
# space only where the result matches a month name (so "Jun e 30" -> "June 30")
# or a known identifier pattern. Every repair is logged: a repair pass we cannot
# inspect is the same hazard as an untested control.
# ---------------------------------------------------------------------------

# Known mojibake -> intended character. Verified against doc 3685's text layer.
_ARTIFACT_MAP = {
    "\u00fb": "-",   # û  en/em dash
    "\u00e6": "'",   # æ  apostrophe (CityÆs -> City's)
    "\u00c6": "'",   # Æ  apostrophe (CityÆs uses Æ before s)
    "\u00ba": "\u00a7",  # º  section sign §
    "\u00f4": '"',   # ô  opening curly double-quote
    "\u00f6": '"',   # ö  closing curly double-quote
    "\u2534": "A",   # ┴  stands in for an accented capital (SÁNCHEZ); best-effort
    "\u00b1": "n",   # ±  stands in for ñ (El Niño); best-effort
    "\u00f2": "\u2022",  # ò  bullet •
}

_MONTHS_ALL = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
# A spurious intra-word space inside a month name: "Jun e", "Sep tember", etc.
# We only repair when joining across the space yields a real month word, so this
# never merges unrelated tokens.
_MONTH_SPACE_FIX = re.compile(
    r"\b([A-Za-z]{2,})\s+([a-z]{1,3})\b"
)


def _repair_for_extraction(text: str) -> str:
    """Return a repaired VIEW of text for entity extraction. Never mutates source.

    Two passes: (1) map known mojibake glyphs; (2) collapse a spurious intra-word
    space when the join forms a month name. Both are logged with before/after so
    what the pass silently fixes is inspectable.
    """
    if not text:
        return text
    repaired = text

    # Pass 1: known artifact glyphs.
    for bad, good in _ARTIFACT_MAP.items():
        if bad in repaired:
            count = repaired.count(bad)
            repaired = repaired.replace(bad, good)
            log.info(
                "entity_repair_artifact",
                artifact=repr(bad),
                intended=repr(good),
                occurrences=count,
            )

    # Pass 2: month-name intra-word space ("Jun e 30" -> "June 30").
    def _join_month(m: re.Match[str]) -> str:
        joined = (m.group(1) + m.group(2))
        if joined.lower() in _MONTHS_ALL and m.group(1).lower() not in _MONTHS_ALL:
            log.info("entity_repair_month_space", before=m.group(0), after=joined)
            return joined
        return m.group(0)

    repaired = _MONTH_SPACE_FIX.sub(_join_month, repaired)
    return repaired


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
    r"\b[A-Z][a-zA-Z]+(?:[^\S\n]+[A-Z][a-zA-Z]+)*[^\S\n]+"
    r"(?:Street|St\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Road|Rd\.?|Drive|Dr\.?|"
    r"Lane|Ln\.?|Way|Court|Ct\.?|Place|Pl\.?)\b"
)
# Proper-noun capture NEVER crosses a newline: a name is within-line. Using
# [^\S\n] (whitespace except newline) as the inter-word gap stops a match from
# spanning "RECOMMENDATION\n\nThe City Council" into one bogus name — the
# over-capture class fixed on real generated rewrites (task 9). An all-caps token
# that ends a line is a header (RECOMMENDATION, staff labels), not part of a name;
# _clean_name drops those too.
_PROPER = re.compile(r"\b[A-Z][a-zA-Z]+(?:[^\S\n]+[A-Z][a-zA-Z]+)+\b")

# Leading determiners/articles are not part of a proper name. A sentence-initial
# "The Council" or Spanish "El Concejo" is a common-noun REFERENCE, not the proper
# name the raw-compare rule targets (which is "Planning Commission", "Main Street").
# Stripping them keeps a correct EN->ES rewrite ("the Council" -> "el Concejo") from
# reading as an invented name.
_LEADING_DET = re.compile(
    r"^(?:the|a|an|el|la|los|las|un|una|unos|unas)\s+", re.IGNORECASE
)

# ROLE NAMES ARE NOT RAW-COMPARE NAMES (calibration decision 1). Job titles and
# role names are common nouns that translate freely — they must NOT be raw-compared
# (that was the dominant known-good rejection). Raw-compare is for person, company,
# org, street, place, and identifier names. This is a spec correction, not a bug.
#
# Two mechanisms:
#   1. Body-name-in-prose that is a pure common-noun reference ("City Council",
#      "el Concejo") is dropped entirely.
#   2. A role TITLE prefixing a person ("City Clerk Michael MacDonald") has the
#      title stripped, leaving the person name — attaching a role to a person is
#      not a new entity as long as the person matches (decision 1).
# "Urban Center Zone" is a zone DESCRIPTION, not an identifier, so it is a common
# noun too; "T5.3" is the identifier and compares raw (handled as it is not a
# multi-word proper-noun span, so it is not captured as a NAME here).

# Common-noun role/body phrases that are never raw-compare entities on their own.
_ROLE_OR_BODY = frozenset(
    {
        "city council", "city clerk", "public works director",
        "chief technology officer", "city manager", "human resources director",
        "chief of police", "mayor", "deputy mayor", "council", "concejo",
        "urban center zone", "land use table",
    }
)

# Role titles that may prefix a person name; stripped so the person name remains.
_ROLE_TITLE_PREFIX = re.compile(
    r"^(?:city\s+clerk|public\s+works\s+director|chief\s+technology\s+officer|"
    r"city\s+manager|human\s+resources\s+director|chief\s+of\s+police|"
    r"deputy\s+mayor|mayor)\s+",
    re.IGNORECASE,
)


def _clean_name(raw: str) -> str | None:
    """Reduce a candidate NAME span to a raw-compare entity, or None to drop it.

    Applies decision 1: drop pure role/body common-noun phrases; strip a leading
    role title off a person name. Returns None when nothing raw-comparable remains.
    """
    name = _LEADING_DET.sub("", raw.strip())
    # An all-caps leading token is a source header/label (RECOMMENDATION, STAFF),
    # not part of a proper name — drop it so it cannot fuse onto a following name.
    name = re.sub(r"^[A-Z]{4,}\s+", "", name).strip()
    # Strip a leading role title so "City Clerk Michael MacDonald" -> "Michael MacDonald".
    name = _ROLE_TITLE_PREFIX.sub("", name).strip()
    if not name:
        return None
    if name.casefold() in _ROLE_OR_BODY:
        return None
    # A single remaining word after stripping is a common noun ("Council"),
    # not a multi-word proper name.
    if len(name.split()) < 2:
        return None
    return name


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
        # Read THROUGH the artifact-repair view; source.text is never mutated.
        text = _repair_for_extraction(text or "")
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
            cleaned = _clean_name(m.group(0))
            if cleaned is None:
                continue
            entities.append(Entity(EntityClass.NAME, cleaned))

        return entities
    except Exception:
        return []
