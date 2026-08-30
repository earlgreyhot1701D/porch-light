"""Entity normalization — the equivalence rule for the verifier (design R3a).

Pure functions, no I/O, no model. This module answers one question: are two
entities *the same fact*, across English and Spanish surface forms?

The rule (recorded here because it is a design decision, not an implementation
detail — check 6 rejected every Spanish rewrite before it existed):

    CLASS    ACTION      WHY
    -----    ------      ---
    DATE     NORMALIZE   "February 10, 2026" and "10 de febrero de 2026" are the
                         same deadline. Canonicalize to ISO 8601 (2026-02-10) so
                         the Spanish translation of a date is not read as a new
                         entity that fails check 6.
    NUMBER   NORMALIZE   "$1.2 million", "1.2 millones", "1,200,000" are the same
                         amount. Canonicalize to a numeric value + unit so the
                         translated magnitude word does not read as drift.
    NAME     COMPARE RAW Proper nouns, person names, street names, body names MUST
                         NOT change in translation. "Main Street" stays
                         "Main Street" in the Spanish rewrite. So names are
                         compared as raw, case-folded, whitespace-collapsed
                         strings — a translated street name is a REAL failure and
                         check 6 is meant to catch it.

The failure this module itself must not commit (it is an invisible-failure
surface, testing.md): a normalizer that OVER-normalizes hides real drift. So
`normalize` is conservative — a value it cannot confidently canonicalize is
returned as its raw, case-folded form, which compares equal only to an identical
raw form, never accidentally equal to a different value. Property 1 pins both
directions: equivalent values normalize equal; genuinely different values do not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from porchlight.verify.entities import Entity, EntityClass

# --- Month name -> month number, English and Spanish. ---
_MONTH_NUM: dict[str, int] = {}
for _i, _name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"),
    start=1,
):
    _MONTH_NUM[_name] = _i
for _i, _name in enumerate(
    ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
     "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
    start=1,
):
    _MONTH_NUM[_name] = _i

_MONTH_ALT = "|".join(_MONTH_NUM.keys())

# "February 10, 2026" or "10 de febrero de 2026" (month + day + year in any order
# our extractor produces).
_DATE_WORDS = re.compile(
    rf"(?P<a>\d{{1,2}}|{_MONTH_ALT})\D+?(?P<b>\d{{1,2}}|{_MONTH_ALT})\D+?(?P<y>\d{{4}})",
    re.IGNORECASE,
)
_DATE_ISO = re.compile(r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})")
_DATE_SLASH = re.compile(r"(?P<m>\d{1,2})[/-](?P<d>\d{1,2})[/-](?P<y>\d{4})")

# Magnitude multipliers (English + Spanish). Ordered LONGEST-FIRST in the alt so
# "million" is tried before "mil" — otherwise "mil" matches the prefix of
# "million" and 1.2 million collapses to 1,200 (a real bug the smoke test caught).
# Word boundaries in the pattern below also guard this.
_MULT = {
    "millones": 1_000_000, "million": 1_000_000, "millon": 1_000_000,
    "billones": 1_000_000_000, "billion": 1_000_000_000,
    "thousand": 1_000, "mil": 1_000,
}
_MULT_ALT = "|".join(sorted(_MULT.keys(), key=len, reverse=True))
# `val` captures digits plus BOTH separators (',' and '.') so a locale-aware
# resolver (_parse_localized_number) can decide thousands-vs-decimal afterward.
# Capturing only one separator here would split "1.200.000" (ES) or "145.800".
_NUM_CORE = re.compile(
    rf"(?P<cur>\$)?\s*(?P<val>\d[\d.,]*)\s*(?:(?P<mult>{_MULT_ALT})\b)?"
    rf"\s*(?P<pct>%|percent|por\s+ciento)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NormalizedEntity:
    """An entity reduced to a comparable canonical form.

    `key` is what equality compares. Two entities are the same fact iff their
    NormalizedEntity keys are equal. `entity_class` is retained so a date is never
    considered equal to a number that happens to share a key.
    """

    entity_class: EntityClass
    key: str


def _norm_date(raw: str) -> str | None:
    """Canonicalize a date to ISO 8601 'YYYY-MM-DD', or None if not confident."""
    low = raw.lower()
    m = _DATE_ISO.search(low)
    if m:
        return f"{int(m['y']):04d}-{int(m['m']):02d}-{int(m['d']):02d}"
    m = _DATE_SLASH.search(low)
    if m:
        return f"{int(m['y']):04d}-{int(m['m']):02d}-{int(m['d']):02d}"
    m = _DATE_WORDS.search(low)
    if m:
        a, b = m["a"], m["b"]
        month = day = None
        for tok in (a, b):
            if tok in _MONTH_NUM:
                month = _MONTH_NUM[tok]
            elif tok.isdigit():
                day = int(tok)
        if month and day and 1 <= day <= 31:
            return f"{int(m['y']):04d}-{month:02d}-{day:02d}"
    return None


def _parse_localized_number(digits: str) -> float | None:
    """Parse a number string that may use EN or ES separator conventions.

    Locale-aware rule (calibration decision, task 8): a '.' or ',' followed by
    EXACTLY three digits and NOT followed by more digits is a THOUSANDS separator;
    a '.' or ',' followed by one or two digits (and no further group) is a DECIMAL.
    So '145.800' (ES) and '145,800' (EN) both yield 145800.0, while '1.5' stays 1.5
    and '1.500' becomes 1500.0. Mixed grouping like '1,200,000' / '1.200.000' folds
    all separators. A genuine decimal like '564.074' with three trailing digits is
    ambiguous with a thousands group; per the rule (exactly-three-digits ⇒
    thousands) it resolves to 564074, which matches the English '$564,074' source —
    the calibration case this rule exists to fix.

    Returns the numeric value, or None if it does not parse.
    """
    s = digits.strip().rstrip(".,")  # drop trailing sentence punctuation
    if not s:
        return None
    # A single separator followed by exactly 1 or 2 digits (end of string) = decimal.
    m_dec = re.fullmatch(r"(\d+)([.,])(\d{1,2})", s)
    if m_dec:
        try:
            return float(f"{m_dec.group(1)}.{m_dec.group(3)}")
        except ValueError:
            return None
    # Otherwise every '.' and ',' is a thousands separator (each group is 3 digits,
    # or it is a bare integer). Strip them and parse as an integer-valued float.
    if re.fullmatch(r"\d{1,3}([.,]\d{3})*", s):
        try:
            return float(re.sub(r"[.,]", "", s))
        except ValueError:
            return None
    # Fallback: strip commas (EN grouping) and try; leaves a lone trailing decimal.
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _norm_number(raw: str) -> str | None:
    """Canonicalize a number to 'value|unit', or None if not confident.

    unit is one of: 'usd' (currency), 'pct' (percent), 'n' (plain). Magnitude
    words are folded into the value so 1.2 million and 1,200,000 collapse.
    Separators are resolved locale-aware (see `_parse_localized_number`), so the
    Spanish thousands-period ('$145.800') matches the English comma ('$145,800').
    """
    m = _NUM_CORE.search(raw.lower())
    if not m or not m["val"]:
        return None
    value = _parse_localized_number(m["val"])
    if value is None:
        return None
    if m["mult"]:
        value *= _MULT[m["mult"].lower()]
    if m["pct"]:
        unit = "pct"
    elif m["cur"]:
        unit = "usd"
    else:
        unit = "n"
    # Integer-valued amounts render without a trailing .0 so 1200000.0 == 1200000.
    if value == int(value):
        return f"{int(value)}|{unit}"
    return f"{value:g}|{unit}"


def _norm_name(raw: str) -> str:
    """Names compare RAW: case-folded and whitespace-collapsed only.

    No translation, no transliteration. This is intentional — a name that changed
    in the Spanish rewrite must fail equality.
    """
    return re.sub(r"\s+", " ", raw.strip()).casefold()


def normalize(entity: Entity) -> NormalizedEntity:
    """Reduce one entity to its canonical comparable form.

    Conservative by design: a date or number that cannot be confidently
    canonicalized falls back to its raw, case-folded form. That form compares
    equal only to an identical raw form — never accidentally equal to a different
    value — so under-normalizing is safe (it can only miss a match, which surfaces
    as a check failure to inspect) while over-normalizing is not (it hides drift).
    """
    raw = entity.raw or ""
    if entity.entity_class is EntityClass.DATE:
        key = _norm_date(raw) or _norm_name(raw)
        return NormalizedEntity(EntityClass.DATE, key)
    if entity.entity_class is EntityClass.NUMBER:
        key = _norm_number(raw) or _norm_name(raw)
        return NormalizedEntity(EntityClass.NUMBER, key)
    return NormalizedEntity(EntityClass.NAME, _norm_name(raw))


def normalize_all(entities: list[Entity]) -> set[NormalizedEntity]:
    """Normalize a list of entities into a set of canonical forms for comparison."""
    return {normalize(e) for e in entities}
