"""Tests for the rewrite pipeline wiring (Spec 3 W1-W2): compose + per-language fallback.

# Feature: 3-extraction, Property 5: never-fail-open rewrite

The invariant under test: the item is ALWAYS present and NEVER carries a rewrite
the verifier rejected. All four language outcomes (EN ok/ES ok, EN ok/ES fail,
EN fail, both fail) keep the item and never fabricate. No live model call — a fake
Converse client returns scripted text so the retry and fallback paths are
deterministic.
"""

from __future__ import annotations

from porchlight.rewrite import pipeline
from porchlight.verify.models import SourceRecord

# A source with a clear entity set; a good rewrite preserves the amount + date.
_SRC = SourceRecord(
    body="city_council",
    meeting_date="2026-08-25",
    item_number="6",
    page_range=(5, 5),
    text=(
        "Authorize a payment of $145,800 to Cognizant Worldwide Limited through "
        "August 31, 2027, increasing the total to $590,130."
    ),
    deadline=None,
    source_url="https://www.cityofventura.ca.gov/doc",
)

_GOOD_EN = "The council may pay $145,800 to Cognizant Worldwide Limited through August 31, 2027, raising the total to $590,130."
_GOOD_ES = "El concejo puede pagar $145.800 a Cognizant Worldwide Limited hasta el 31 de agosto de 2027, elevando el total a $590.130."
# A genuinely-rejectable rewrite: invents a dollar amount ($999,999) absent from
# source, so check 2 / check 6 reject it. (A vague sentence with NO extractable
# entities would wrongly PASS entity checks — the bad rewrite must carry a WRONG
# entity, the way the golden adversarial does.)
_BAD = "The council will authorize a payment of $999,999 to a different vendor."


class FakeClient:
    """A stubbed bedrock-runtime client: returns scripted texts in call order."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.calls = 0

    def converse(self, **kwargs):
        text = self._texts[min(self.calls, len(self._texts) - 1)]
        self.calls += 1
        return {
            "output": {"message": {"content": [{"text": text}]}},
            "usage": {"inputTokens": 10, "outputTokens": 5},
        }


def test_both_verify_first_try():
    client = FakeClient([_GOOD_EN, _GOOD_ES])
    r = pipeline.rewrite_item(_SRC, client=client)
    assert r.en_verified and r.es_verified
    assert r.en_text == _GOOD_EN
    assert r.es_text == _GOOD_ES
    assert r.en_attempts == 1 and r.es_attempts == 1


def test_en_ok_es_recovers_on_retry():
    # EN good; ES bad first, good on retry.
    client = FakeClient([_GOOD_EN, _BAD, _GOOD_ES])
    r = pipeline.rewrite_item(_SRC, client=client)
    assert r.en_verified and r.es_verified
    assert r.es_attempts == 2


def test_en_ok_es_fails_twice_falls_back_to_english():
    # EN good; ES bad both times -> ES absent, verified English shown, item present.
    client = FakeClient([_GOOD_EN, _BAD, _BAD])
    r = pipeline.rewrite_item(_SRC, client=client)
    assert r.en_verified is True
    assert r.es_verified is False
    assert r.es_text is None
    assert r.shown_english == _GOOD_EN
    assert "verified Spanish version was not produced" in r.es_absent_note
    # Never carries the unverified ES rewrite.
    assert _BAD not in (r.es_text or "")


def test_en_fails_twice_shows_original_and_no_spanish():
    # EN bad both times -> original English staff text, ES absent, item still present.
    client = FakeClient([_BAD, _BAD])
    r = pipeline.rewrite_item(_SRC, client=client)
    assert r.en_verified is False
    assert r.en_text == _SRC.text  # original staff text, not the rewrite
    assert r.es_verified is False and r.es_text is None
    assert r.note_en and r.es_absent_note
    # The bad rewrite is never shown.
    assert r.en_text != _BAD


def test_item_always_present_and_never_unverified():
    """Property: across every outcome, the item exists and no shown text is an
    unverified rewrite."""
    scenarios = [
        [_GOOD_EN, _GOOD_ES],   # both ok
        [_GOOD_EN, _BAD, _BAD], # es fails
        [_BAD, _BAD],           # en fails
    ]
    for texts in scenarios:
        r = pipeline.rewrite_item(_SRC, client=FakeClient(texts))
        assert r.source is _SRC              # item present
        assert r.shown_english              # always something in English
        if not r.es_verified:
            assert r.es_text is None        # never an unverified ES rewrite
        if not r.en_verified:
            assert r.en_text == _SRC.text   # original, never the rejected rewrite
