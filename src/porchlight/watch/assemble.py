"""Assemble a ChangedItem card from a match + the record (R6, never.md #1/#6/#7).

Pure functions, no model, no I/O. This is the seam where the model's reason meets
the code's receipt: the receipt, deadline, page range, and shown summary come ONLY
from the stored record (never.md #6), and the model's contribution is exactly the
`match_reason`. A receipt is never model-authored because the model never had a
field to write one into (models.py) and this function reads receipt fields only
from the record row.

Shown summary (R6.5, never.md #7): the VERIFIED rewrite from the record, or the
stored honest fallback text — never re-summarized here. Deadline (R6.3, never.md
#1): copied from source or None; the reserved amber (`deadline_actionable`) is set
ONLY for an approaching, still-actionable comment deadline (voice.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from porchlight.deadline.render import Language as DLang
from porchlight.deadline.render import render as render_deadline
from porchlight.draft.scaffold import build_scaffold
from porchlight.verify.models import SourceRecord
from porchlight.watch.models import WatchMatch
from porchlight.web.contract import (
    Bilingual,
    ChangedItem,
    Mark,
    Receipt,
    Tone,
)


@dataclass(frozen=True)
class RecordRow:
    """The stored facts an item carries — all copied from items/meetings/bodies/docs.

    This is the record side of the seam: every field here is deterministic, from the
    database, never from the model. `en_summary`/`es_summary` are the VERIFIED
    rewrites (or the stored honest fallback text). `deadline` is a tz-aware instant
    copied from source, or None. `official_term` is the plain/official pair.
    """

    item_id: str
    body_name: str
    meeting_date: str
    item_number: str
    page_range: tuple[int, int]
    source_url: str
    en_summary: str
    es_summary: str
    heading_en: str
    heading_es: str
    official_term_en: str
    official_term_es: str
    scale_note_en: str
    scale_note_es: str
    deadline: datetime | None = None
    en_summary_verified: bool = True
    es_summary_verified: bool = True


def _receipt_line(row: RecordRow, lang: str) -> str:
    """The mono receipt line: body · meeting date · item # · page range (from record)."""
    p0, p1 = row.page_range
    pages = f"p. {p0}" if p0 == p1 else f"pp. {p0}-{p1}"
    item = f"Item {row.item_number}" if lang == "en" else f"Punto {row.item_number}"
    return f"{row.body_name} · {row.meeting_date} · {item} · {pages}"


def _source_href(row: RecordRow) -> str:
    """Anchor the source link to the item's first page when possible (ui-contract)."""
    p0 = row.page_range[0]
    if row.source_url and p0 >= 1:
        sep = "&" if "?" in row.source_url else "#"
        return f"{row.source_url}{sep}page={p0}"
    return row.source_url


def assemble_card(
    match: WatchMatch,
    row: RecordRow,
    *,
    now: datetime | None = None,
    deadline_actionable_window_days: int = 14,
) -> ChangedItem:
    """Build the ChangedItem contract card for one match (R6.1).

    The ONLY field taken from `match` is the reason (`match.reason`). Everything
    else — status, official term, heading, scale note, receipt, deadline, summary —
    comes from `row` (the record). The draft action is offered; the scaffold itself
    is built on demand by `build_draft` (below), stance-empty, no send.

    `deadline_actionable` (the reserved amber, voice.md) is True ONLY when a deadline
    exists AND is in the future within the actionable window — an approaching comment
    deadline the user can still act on. A past or absent deadline never lights amber.
    """
    receipt = Receipt(
        line=Bilingual(en=_receipt_line(row, "en"), es=_receipt_line(row, "es")),
        source_href=_source_href(row),
        source_label=Bilingual(en="Open the city document", es="Abrir el documento de la ciudad"),
    )

    # Deadline: copied from source or None (never.md #1). Rendered city-local labeled.
    deadline_bilingual: Bilingual | None = None
    actionable = False
    if row.deadline is not None:
        ref = now or datetime.now(row.deadline.tzinfo)
        en = render_deadline(row.deadline, ref, DLang.EN)
        es = render_deadline(row.deadline, ref, DLang.ES)
        deadline_bilingual = Bilingual(
            en=f"{en.absolute} — {en.relative}",
            es=f"{es.absolute} — {es.relative}",
        )
        days = (row.deadline.date() - ref.astimezone(row.deadline.tzinfo).date()).days
        actionable = 0 <= days <= deadline_actionable_window_days

    tone = Tone.HOT if actionable else Tone.CALM

    return ChangedItem(
        id=row.item_id,
        tone=tone,
        mark=Mark.ADDED,
        status=Bilingual(en="New material added", es="Material nuevo agregado"),
        official_term=Bilingual(en=row.official_term_en, es=row.official_term_es),
        heading=Bilingual(en=row.heading_en, es=row.heading_es),
        match_reason=Bilingual(en=match.reason.en, es=match.reason.es),
        scale_note=Bilingual(en=row.scale_note_en, es=row.scale_note_es),
        receipt=receipt,
        deadline=deadline_bilingual,
        deadline_actionable=actionable,
        action=Bilingual(en="Start a comment", es="Comenzar un comentario"),
    )


def build_draft(row: RecordRow, *, how_to_submit: str, where_to_submit: str):
    """Build the stance-free draft scaffold for a card's 'Start a comment' action.

    Wires the existing `draft.scaffold.build_scaffold` (never.md #4/#5: empty stance,
    no send). The verified summary and receipt come from the record; nothing here
    accepts a position. Deadline is passed as the source string form (or empty).
    """
    source = SourceRecord(
        body=row.body_name,
        meeting_date=row.meeting_date,
        item_number=row.item_number,
        page_range=row.page_range,
        text="",  # the scaffold uses the verified summary, not raw text
        deadline=(row.deadline.isoformat() if row.deadline else None),
        source_url=row.source_url,
    )
    return build_scaffold(
        verified_summary=row.en_summary,
        source=source,
        how_to_submit=how_to_submit,
        where_to_submit=where_to_submit,
    )
