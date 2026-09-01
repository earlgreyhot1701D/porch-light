"""The watcher's structured output types (R1.1, R1.3, R6.1, never.md #10).

Frozen dataclasses, no model, no I/O. Two guarantees encoded in the TYPES:

  1. **Match and reason are one object (never.md #10).** A `WatchMatch` cannot be
     constructed without its `reason` — reason is a required positional field. There
     is no code path that produces a match and then fills a reason in a second call;
     a post-hoc explanation is confabulation and the type forbids it.

  2. **The model has no field to author a receipt into (never.md #6).** `WatchMatch`
     carries only what the MODEL legitimately produces: which item matched (by id)
     and why (plain-language, bilingual). It has NO body / meeting-date / item-number
     / page-range / deadline / URL field. Those are the receipt, attached later from
     the record by `assemble.py` — the model cannot write them because they do not
     exist here to write.

The `reason` is bilingual and carries NO receipt entities (R1.3): no date, deadline,
item number, page range, body name, or URL. It says why the item is relevant to a
watch term, in plain language, and nothing a resident could act on lives in it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BilingualReason:
    """The plain-language match reason, English and Spanish, equal weight (voice.md).

    Emitted by the matcher in ONE structured output (never a follow-up translation
    call, R9.3). Carries no receipt entities (R1.3).
    """

    en: str
    es: str


@dataclass(frozen=True)
class WatchMatch:
    """One relevant item for a watchlist: WHICH item, and WHY — in one object.

    `item_id` names the matched stored item (its receipt/summary are fetched from the
    record downstream). `reason` is required — there is no default and no setter, so a
    match without a reason is not constructable (never.md #10). `matched_terms` are
    the watch terms this item is relevant to (from the browser watchlist, not new
    facts). There is deliberately NO receipt/deadline/body/page field here.
    """

    item_id: str
    reason: BilingualReason
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class WatchAnswer:
    """The watcher's whole answer for one watchlist over the stored items.

    `matches` may be empty — an empty match set with `degraded=False` is the honest
    QUIET result (looked, found nothing). `is_partial` True means a cap fired before
    the full item set was assessed; the matches found so far STAND and are returned,
    never discarded (R1.4). `degraded` True means a dependency failed and we could
    NOT fully look — an honest degraded state, distinct from quiet, never a
    fabricated match and never a silent all-clear (R5.2, never.md #7). `note` carries
    a short, non-fabricated explanation for the partial/degraded case.
    """

    matches: tuple[WatchMatch, ...] = ()
    is_partial: bool = False
    degraded: bool = False
    note: str = ""

    @property
    def is_quiet(self) -> bool:
        """True iff we looked fully and found nothing (not degraded, not partial)."""
        return not self.matches and not self.degraded and not self.is_partial
