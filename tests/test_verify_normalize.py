"""Property + example tests for the entity normalizer.

# Feature: 3-extraction, Property 1: entity normalizer

The normalizer is an invisible-failure surface twice over: under-normalize and a
Spanish rewrite's translated date reads as a new entity (check 6 rejects every
Spanish rewrite — the bug this module was written to kill); over-normalize and a
genuinely changed number or a translated street name reads as equal, hiding real
drift the verifier is supposed to catch.

The property, pinned in both directions:
  - EN/ES equivalent dates and numbers normalize EQUAL.
  - Genuinely different values do NOT (no over-normalization).
  - A translated proper noun / street name does NOT match (names compare raw).

Example tests pin the concrete surface forms from the design table.
"""

from __future__ import annotations

from datetime import date

from hypothesis import given, strategies as st

from porchlight.verify.entities import Entity, EntityClass, extract
from porchlight.verify.normalize import normalize, normalize_all


# --- Example tests: the design-table surface forms ---

def test_date_en_es_equivalent():
    en = normalize_all(extract("due February 10, 2026"))
    es = normalize_all(extract("vence el 10 de febrero de 2026"))
    assert en == es
    assert en == {normalize(Entity(EntityClass.DATE, "2026-02-10"))}


def test_date_numeric_forms_equivalent():
    slash = normalize_all(extract("hearing 02/10/2026"))
    iso = normalize_all(extract("hearing 2026-02-10"))
    assert slash == iso


def test_currency_millions_en_es_equivalent():
    en = normalize_all(extract("costs $1.2 million"))
    es = normalize_all(extract("cuesta $1.2 millones"))
    plain = normalize_all(extract("$1,200,000"))
    assert en == es == plain


def test_thousand_mil_not_confused_with_million():
    # Regression: 'mil' once matched the prefix of 'million' and 1.2M collapsed to 1200.
    assert normalize_all(extract("5 thousand")) == normalize_all(extract("5 mil"))
    assert normalize_all(extract("1.2 million")) != normalize_all(extract("1.2 thousand"))


def test_percent_en_es_equivalent():
    assert normalize_all(extract("45 percent")) == normalize_all(extract("45 por ciento"))


def test_different_amount_not_equal():
    assert normalize_all(extract("$1.2 million")) != normalize_all(extract("$1.3 million"))


def test_translated_street_name_not_equal():
    # A street name that changed in translation is a REAL failure; check 6 must catch it.
    en = normalize_all(extract("the property on Main Street"))
    es = normalize_all(extract("la propiedad en Calle Principal"))
    assert en != es


def test_same_street_name_unchanged_matches():
    # Correctly-left-untranslated name matches across languages.
    en = normalize_all(extract("the property on Main Street"))
    es = normalize_all(extract("la propiedad en Main Street"))
    assert en == es


# --- Property tests ---

@st.composite
def _iso_date(draw) -> date:
    return draw(st.dates(min_value=date(2024, 1, 1), max_value=date(2030, 12, 31)))


_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)
_MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


@given(_iso_date())
def test_property_date_en_es_forms_normalize_equal(d: date):
    """Any date, written English-style and Spanish-style, normalizes to the same ISO key."""
    en_form = f"{_MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    es_form = f"{d.day} de {_MONTHS_ES[d.month - 1]} de {d.year}"
    en = normalize_all(extract(en_form))
    es = normalize_all(extract(es_form))
    assert en == es
    iso = f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
    assert any(ne.key == iso for ne in en)


@given(
    st.integers(min_value=10, max_value=999_999),
    st.integers(min_value=10, max_value=999_999),
)
def test_property_different_amounts_never_collapse(a: int, b: int):
    """Two genuinely different multi-digit amounts never normalize to the same key.

    Range starts at 10: the extractor deliberately treats a lone single digit
    ("phase 2", "option 1") as NOT a receipt-critical entity (entities.py's
    interesting-number rule requires a currency sign, magnitude word, percent, a
    decimal, or two-plus digits). Sub-threshold digits are covered by the separate
    assertion below, so this property tests the class the extractor actually
    captures — no over-normalization within it.
    """
    na = normalize_all(extract(f"amount ${a}"))
    nb = normalize_all(extract(f"amount ${b}"))
    if a != b:
        assert na != nb
    else:
        assert na == nb


def test_single_digit_bare_number_is_not_an_entity():
    """A lone single digit is intentionally not extracted as a receipt entity.

    Documents the deliberate floor: "option 1" / "phase 2" are not amounts the
    verifier must preserve. A single digit that IS receipt-critical carries a
    currency sign or unit and is then captured (e.g. '$2').
    """
    assert normalize_all(extract("option 1")) == set()
    assert normalize_all(extract("phase 2")) == set()
    # With a currency sign it becomes an entity again.
    assert normalize_all(extract("$2")) != set()


@given(st.integers(min_value=1_000, max_value=999_999))
def test_property_thousand_word_equals_numeric(n: int):
    """'N thousand' equals the numeric value N*1000 (magnitude folded, currency-free)."""
    word = normalize_all(extract(f"{n} thousand"))
    numeric = normalize_all(extract(f"{n * 1000}"))
    assert word == numeric


@given(st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=2, max_size=8))
def test_property_name_never_matches_a_different_name(word: str):
    """A capitalized name never normalizes equal to a different capitalized name (raw compare)."""
    other = word + "x"
    n1 = normalize(Entity(EntityClass.NAME, f"{word.capitalize()} Street"))
    n2 = normalize(Entity(EntityClass.NAME, f"{other.capitalize()} Street"))
    assert n1 != n2
