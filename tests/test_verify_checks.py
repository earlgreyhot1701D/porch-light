"""Property + example tests for the six verifier checks.

# Feature: 3-extraction, Property 2: verifier checks

The verifier is the product's spine. A check that PASSES a rewrite it should
reject is the worst invisible failure available: a fabricated summary shipped with
a receipt (§28). So each adversarial case from the design (added entity, dropped
date, altered amount, unsimplified copy, ES changed number, ES translated street
name) must be REJECTED, and a known-good rewrite must PASS.

Reading-level thresholds are NOT the golden-set-derived production values here
(that is calibration, task 8); these tests pass an explicit floor and focus on the
check's LOGIC (below floor fails; not-simpler-than-source fails; simpler passes).
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from porchlight.verify import checks
from porchlight.verify.models import Language, Rewrite, SourceRecord

# A realistic source record. Reading floor for tests is a low, explicit value so
# the reading check's LOGIC is exercised, not a production threshold.
_SOURCE = SourceRecord(
    body="Planning Commission",
    meeting_date="2026-02-10",
    item_number="7",
    page_range=(4, 5),
    text=(
        "Item 7. The Commission shall consider the adoption of an ordinance "
        "authorizing a grant in the amount of $1.2 million for the rehabilitation "
        "of the property located on Main Street, and further providing that public "
        "comment shall be received until February 10, 2026, in accordance with "
        "applicable provisions of the municipal code."
    ),
    deadline="2026-02-10",
    source_url="https://www.cityofventura.ca.gov/doc",
)

_TEST_FLOOR = 10.0

_GOOD_EN = Rewrite(
    Language.EN,
    "The Commission may approve a $1.2 million grant to fix up the Main Street "
    "property. You can comment until February 10, 2026.",
)
_GOOD_ES = Rewrite(
    Language.ES,
    "La Comision puede aprobar una subvencion de $1.2 millones para arreglar la "
    "propiedad en Main Street. Puede comentar hasta el 10 de febrero de 2026.",
)


# --- Check 1: schema ---

def test_schema_passes_valid():
    assert checks.check_schema(_GOOD_EN).passed


def test_schema_rejects_empty():
    assert not checks.check_schema(Rewrite(Language.EN, "   ")).passed


# --- Check 2: entity preservation (added / altered value) ---

def test_entity_preservation_passes_good():
    assert checks.check_entity_preservation(_GOOD_EN, _SOURCE).passed


def test_entity_preservation_rejects_altered_amount():
    bad = Rewrite(Language.EN, "The Commission may approve a $5 million grant on Main Street.")
    assert not checks.check_entity_preservation(bad, _SOURCE).passed


def test_entity_preservation_rejects_invented_date():
    bad = Rewrite(Language.EN, "Comment until March 3, 2027 on the Main Street grant.")
    assert not checks.check_entity_preservation(bad, _SOURCE).passed


# --- Check 3: no new entities ---

def test_no_new_entities_passes_good():
    assert checks.check_no_new_entities(_GOOD_EN, _SOURCE).passed


def test_no_new_entities_rejects_added_entity():
    bad = Rewrite(Language.EN, "The Commission grant covers Main Street and Oak Avenue.")
    assert not checks.check_no_new_entities(bad, _SOURCE).passed


# --- Check 4: containment (receipt drift) ---

def test_containment_passes_matching_claim():
    r = Rewrite(Language.EN, _GOOD_EN.summary, claimed_item_number="7", claimed_page_range=(4, 5))
    assert checks.check_containment(r, _SOURCE).passed


def test_containment_rejects_wrong_item_number():
    r = Rewrite(Language.EN, _GOOD_EN.summary, claimed_item_number="9")
    assert not checks.check_containment(r, _SOURCE).passed


def test_containment_rejects_wrong_page_range():
    r = Rewrite(Language.EN, _GOOD_EN.summary, claimed_page_range=(1, 2))
    assert not checks.check_containment(r, _SOURCE).passed


# --- Check 5: reading level (below floor / not simpler / simpler) ---

def test_reading_level_rejects_unsimplified_copy():
    # A rewrite that is just the dense source copied is not simpler than itself.
    copy = Rewrite(Language.EN, _SOURCE.text)
    assert not checks.check_reading_level(copy, _SOURCE, _TEST_FLOOR).passed


def test_reading_level_passes_simpler_rewrite():
    assert checks.check_reading_level(_GOOD_EN, _SOURCE, _TEST_FLOOR).passed


def test_reading_level_rejects_below_floor():
    # An impossibly high floor rejects even a good rewrite (floor logic).
    assert not checks.check_reading_level(_GOOD_EN, _SOURCE, 999.0).passed


# --- Check 6: both languages (translated name / changed number) ---

def test_both_languages_passes_good_spanish():
    assert checks.check_both_languages(_GOOD_ES, _SOURCE).passed


def test_both_languages_rejects_translated_street_name():
    bad = Rewrite(
        Language.ES,
        "La Comision puede aprobar $1.2 millones para la propiedad en Calle Principal "
        "hasta el 10 de febrero de 2026.",
    )
    assert not checks.check_both_languages(bad, _SOURCE).passed


def test_both_languages_rejects_changed_number():
    bad = Rewrite(
        Language.ES,
        "La Comision puede aprobar $5 millones para la propiedad en Main Street "
        "hasta el 10 de febrero de 2026.",
    )
    assert not checks.check_both_languages(bad, _SOURCE).passed


# --- Property: a known-good rewrite passes every check; corruptions are rejected ---

def test_property_good_rewrite_passes_all_checks():
    assert checks.check_schema(_GOOD_EN).passed
    assert checks.check_entity_preservation(_GOOD_EN, _SOURCE).passed
    assert checks.check_no_new_entities(_GOOD_EN, _SOURCE).passed
    assert checks.check_reading_level(_GOOD_EN, _SOURCE, _TEST_FLOOR).passed
    assert checks.check_both_languages(_GOOD_ES, _SOURCE).passed


@given(st.sampled_from([5, 7, 9, 42, 100]).map(lambda n: f"${n} million"))
def test_property_any_wrong_amount_rejected(wrong_amount: str):
    """Any dollar amount not in the source is rejected by entity preservation."""
    bad = Rewrite(Language.EN, f"The Commission may approve a {wrong_amount} grant on Main Street.")
    # $1.2 million is the only amount in source; these are all different.
    assert not checks.check_entity_preservation(bad, _SOURCE).passed
