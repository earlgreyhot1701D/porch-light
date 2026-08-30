"""The read-only view contract (R6, §25) — the JSON the public site consumes.

Pure data models + serialization, no I/O, no model. This is the bridge in the
contract-first plan: the accepted mock renders from `fixtures/sample.json` shaped
to THIS contract, and the Spec 6 live endpoint returns the same shape, so wiring
is a path swap, not a reshape (§25). The field set is copied from the accepted
mock's changed-card / receipt / quiet-week structure (ui-contract.md) — view
structure is not invented here.

Every user-facing string is bilingual by construction: a `Bilingual` carries `en`
and `es` with equal weight (voice.md). The mock indirects through a COPY table by
`*Key`; the live/fixture contract instead carries the resolved `{en, es}` values
inline, which is what an API returns and what the fixture must contain so wiring
is a path swap.

Load-bearing rules encoded here, not left to the renderer:
  - Absence is `"not located at [url] as of [timestamp]"` — never missing/overdue
    (voice.md, never.md #3). The `SourceStatus.evidence` field is exactly this.
  - `--deadline` amber is for an APPROACHING, still-actionable comment deadline
    only. The contract carries `deadline_actionable: bool` so the renderer applies
    the reserved token by data, never by guessing; status also carries a word +
    shape, so meaning survives greyscale (voice.md).
  - Receipt fields are copied from the record (never.md #6); the contract has no
    field a model could author a receipt into.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Bilingual:
    """A user-facing string in both languages, equal weight (voice.md)."""

    en: str
    es: str

    def as_dict(self) -> dict[str, str]:
        return {"en": self.en, "es": self.es}


class Tone(str, Enum):
    """Card tone. `hot` is the only tone that may carry the reserved deadline amber,
    and only when the deadline is still actionable (voice.md)."""

    HOT = "hot"
    CALM = "calm"


class Mark(str, Enum):
    """The status SHAPE (survives greyscale, pairs with a word — never colour alone)."""

    ADDED = "added"
    OFF = "off"


@dataclass(frozen=True)
class Receipt:
    """The receipt component (ui-contract): mono line + jump-to-source link.

    `line` is the resolved receipt text (body · meeting date · item # · page range),
    all copied from the record. `source_href` is the city document URL, ideally
    anchored to the page (`#page=NNN`). `source_label` is the link's accessible text.
    """

    line: Bilingual
    source_href: str
    source_label: Bilingual

    def as_dict(self) -> dict:
        return {
            "line": self.line.as_dict(),
            "source_href": self.source_href,
            "source_label": self.source_label.as_dict(),
        }


@dataclass(frozen=True)
class ChangedItem:
    """One card in the 'changed' state — a match on the watcher's list.

    Field set mirrors the mock's CHANGED_DATA + COPY entries (ui-contract): status
    chip + adjacent official term, heading, why-it-matched line, page-scale note,
    receipt, deadline, and one action. `deadline` is copied from source (never.md
    #1); `deadline_actionable` gates the reserved amber token by DATA.
    """

    id: str
    tone: Tone
    mark: Mark
    status: Bilingual
    """The chip word, e.g. 'New material added' (survives greyscale with `mark`)."""

    official_term: Bilingual
    """Plain term with the official term adjacent (voice.md): 'Official term: Supplemental packet'."""

    heading: Bilingual
    match_reason: Bilingual
    """Why this matched the watch — emitted with the match (never a second call, never.md #10)."""

    scale_note: Bilingual
    """e.g. 'This packet is 312 pages. The item shown here is 13 pages.'"""

    receipt: Receipt
    deadline: Bilingual | None
    """Rendered deadline string (city-local, labeled) or None if source states none."""

    deadline_actionable: bool = False
    """True only for an approaching deadline the user can still act on (gates amber)."""

    action: Bilingual | None = None
    """The single card action label, e.g. 'Start a comment', or None."""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tone": self.tone.value,
            "mark": self.mark.value,
            "status": self.status.as_dict(),
            "official_term": self.official_term.as_dict(),
            "heading": self.heading.as_dict(),
            "match_reason": self.match_reason.as_dict(),
            "scale_note": self.scale_note.as_dict(),
            "receipt": self.receipt.as_dict(),
            "deadline": self.deadline.as_dict() if self.deadline else None,
            "deadline_actionable": self.deadline_actionable,
            "action": self.action.as_dict() if self.action else None,
        }


@dataclass(frozen=True)
class SourceStatus:
    """A recent-checks row (quiet-week 'Recent checks'). Absence is honest, never scolding.

    When a body could not be read, `evidence` is EXACTLY the voice.md form
    "not located at [url] as of [timestamp]" — never "missing/overdue/failed"
    (never.md #3). `datetime` is an ISO string for the `<time datetime>` element.
    """

    datetime: str
    date: Bilingual
    time: str
    body: Bilingual
    evidence: Bilingual | None = None
    """The 'not located at [url] as of [timestamp]' line, or None when the read succeeded."""

    def as_dict(self) -> dict:
        return {
            "datetime": self.datetime,
            "date": self.date.as_dict(),
            "time": self.time,
            "body": self.body.as_dict(),
            "evidence": self.evidence.as_dict() if self.evidence else None,
        }


@dataclass(frozen=True)
class Heartbeat:
    """The system heartbeat panel: when the city was read and how many bodies."""

    city_read: Bilingual
    read_count: Bilingual
    next_check: Bilingual

    def as_dict(self) -> dict:
        return {
            "city_read": self.city_read.as_dict(),
            "read_count": self.read_count.as_dict(),
            "next_check": self.next_check.as_dict(),
        }


@dataclass(frozen=True)
class View:
    """The whole read-only view: the quiet-week default plus any changed items.

    `is_quiet` True is the most-seen, deliberately-designed screen (ui-contract):
    an honest 'nothing new' is the product working, not failing. `changed` is empty
    on a quiet week. `synthetic` marks fixture data with no real instance yet (§25),
    so the sample-data notice can stay honest until the data is real.
    """

    is_quiet: bool
    heartbeat: Heartbeat
    recent_checks: tuple[SourceStatus, ...] = ()
    changed: tuple[ChangedItem, ...] = ()
    synthetic: bool = False

    def as_dict(self) -> dict:
        return {
            "is_quiet": self.is_quiet,
            "heartbeat": self.heartbeat.as_dict(),
            "recent_checks": [s.as_dict() for s in self.recent_checks],
            "changed": [c.as_dict() for c in self.changed],
            "synthetic": self.synthetic,
        }
