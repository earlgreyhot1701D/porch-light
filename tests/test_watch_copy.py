"""Bilingual coverage + verbatim privacy string (Spec 5 task 7.2, R3.4/R9, voice.md)."""
from __future__ import annotations

import pathlib

from porchlight.watch import copy as C


def test_every_watcher_string_has_en_and_es():
    for b in C.ALL_STRINGS:
        assert b.en.strip(), f"missing EN for {b!r}"
        assert b.es.strip(), f"missing ES for {b!r}"
        assert b.en != b.es, f"EN and ES identical (untranslated?): {b.en!r}"


def test_privacy_string_is_exactly_the_approved_wording():
    # Verbatim (voice.md) — byte-for-byte, do not "improve".
    assert C.PRIVACY.en == "Your list stays on your device. We use it to answer, and never store it."


def test_no_code_claims_we_never_see_the_list():
    # The old untrue wording must not reappear anywhere in the watch package
    # (voice.md §26c: the watcher matches from a transmitted list, so "never see" is false).
    watch_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "porchlight" / "watch"
    for path in watch_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "never see" not in text, f"{path.name} claims 'never see' the list (untrue, voice.md)"
        assert "we never see it" not in text


def test_greeting_is_the_provisional_es():
    assert C.GREETING.es == "Buenas tardes, vecindad."
