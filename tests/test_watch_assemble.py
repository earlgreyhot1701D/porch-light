"""Tests for card assembly (Spec 5 task 4.3, R6.2/R6.3/R6.5, never.md #1/#6/#7)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from porchlight.watch.assemble import RecordRow, assemble_card, build_draft
from porchlight.watch.models import BilingualReason, WatchMatch

CITY = ZoneInfo("America/Los_Angeles")


def _row(**over) -> RecordRow:
    base = dict(
        item_id="3685-6", body_name="City Council", meeting_date="2026-08-25",
        item_number="6", page_range=(5, 5),
        source_url="https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08252026-3685",
        en_summary="The City Council will consider extending a contract.",
        es_summary="El Concejo Municipal considerara extender un contrato.",
        heading_en="Contract extension", heading_es="Extension de contrato",
        official_term_en="Official term: First Amendment",
        official_term_es="Termino oficial: Primera Enmienda",
        scale_note_en="This item is 1 page.", scale_note_es="Este punto tiene 1 pagina.",
    )
    base.update(over)
    return RecordRow(**base)


def _match() -> WatchMatch:
    return WatchMatch(item_id="3685-6", reason=BilingualReason(en="matches your contract watch", es="coincide"))


def test_receipt_copied_from_record_not_from_match():
    card = assemble_card(_match(), _row())
    assert "City Council" in card.receipt.line.en
    assert "Item 6" in card.receipt.line.en
    assert "pp. 5-5" in card.receipt.line.en or "p. 5" in card.receipt.line.en
    # The reason is the ONLY thing from the match.
    assert card.match_reason.en == "matches your contract watch"
    # Source link is anchored to the page.
    assert "page=5" in card.receipt.source_href


def test_no_deadline_means_no_amber():
    card = assemble_card(_match(), _row(deadline=None))
    assert card.deadline is None
    assert card.deadline_actionable is False
    assert card.tone.value == "calm"


def test_approaching_deadline_lights_amber():
    now = datetime(2026, 8, 25, 9, 0, tzinfo=CITY)
    dl = datetime(2026, 8, 30, 17, 0, tzinfo=CITY)  # 5 days out, within window
    card = assemble_card(_match(), _row(deadline=dl), now=now)
    assert card.deadline is not None
    assert card.deadline_actionable is True
    assert card.tone.value == "hot"
    assert "Pacific" in card.deadline.en  # city-local, labeled


def test_past_deadline_does_not_light_amber():
    now = datetime(2026, 8, 25, 9, 0, tzinfo=CITY)
    dl = datetime(2026, 8, 20, 17, 0, tzinfo=CITY)  # already closed
    card = assemble_card(_match(), _row(deadline=dl), now=now)
    assert card.deadline_actionable is False
    assert card.tone.value == "calm"


def test_draft_is_stance_empty_and_has_no_send():
    scaffold = build_draft(_row(), how_to_submit="Email the clerk", where_to_submit="clerk@ventura.example")
    assert scaffold.is_stance_empty()
    # No send capability anywhere on the scaffold.
    assert not any("send" in name.lower() for name in dir(scaffold))
    assert scaffold.item_summary  # carries the verified summary


def test_card_serializes_to_contract_shape():
    card = assemble_card(_match(), _row())
    d = card.as_dict()
    for key in ("id", "match_reason", "receipt", "deadline", "deadline_actionable", "action"):
        assert key in d
    assert d["match_reason"] == {"en": "matches your contract watch", "es": "coincide"}
