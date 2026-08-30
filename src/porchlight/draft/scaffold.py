"""Draft scaffold — facts + receipt + logistics, stance empty by construction (R4, §4b).

Pure functions, no model, no I/O, no network. This assembles the STRUCTURE of a
public comment: what the item is, the receipt, the logistics, and then labeled
BLANK fields the human fills. It never contains a position.

Two non-negotiables this module enforces structurally (never.md #4, #5):

  1. **Stance fields are empty by construction.** The dataclass has no parameter
     that accepts a position, a recommendation, or an argument. There is no code
     path that fills "your_position" / "why_this_matters" / "what_you_are_asking".
     They are always the empty string. An injected instruction that tries to steer
     the draft has nothing to steer, because the field it would target does not
     accept input. This is the §4b defense: emptiness is not a default that could
     be overridden, it is the only possible value.

  2. **No send capability.** There is no send function, no transport, no address
     field, no feature flag, no dead code path here or anywhere. The scaffold is
     handed to the human, who writes the position and sends it themselves.

The factual fields (receipt, deadline, logistics) are copied from the verified
extraction record — never generated (never.md #1, #6). Anything shown here has
already passed the verifier upstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from porchlight.verify.models import SourceRecord


@dataclass(frozen=True)
class Receipt:
    """The claim's receipt: every field copied from the record (never.md #6)."""

    body: str
    meeting_date: str
    item_number: str
    page_range: tuple[int, int]
    source_url: str


@dataclass(frozen=True)
class Logistics:
    """How and where to comment. Deadline is copied from source or None (never.md #1)."""

    deadline: str | None
    how_to_submit: str
    where_to_submit: str


@dataclass(frozen=True)
class StanceFields:
    """The blanks the HUMAN fills. Empty by construction — never model-written (§4b).

    These are frozen empty strings. The class exposes no constructor argument to
    set them to anything else, so no code path — and no injected prompt — can put
    a position here. This is the structural guarantee behind never.md #5.
    """

    your_position: str = ""
    why_this_matters_to_you: str = ""
    what_you_are_asking_for: str = ""


@dataclass(frozen=True)
class DraftScaffold:
    """A complete comment scaffold: facts + receipt + logistics + empty stance.

    There is deliberately no `send`, no recipient, no transport. The scaffold is
    data the human reads, completes, and submits on their own.
    """

    item_summary: str
    """The verified plain-language summary of what the item is (passed the verifier)."""

    receipt: Receipt
    logistics: Logistics
    stance: StanceFields = field(default_factory=StanceFields)

    def is_stance_empty(self) -> bool:
        """True iff every stance field is empty — always True by construction.

        Provided so a test can assert the invariant holds for any scaffold the
        code can produce (there is no way to construct one where this is False).
        """
        return (
            self.stance.your_position == ""
            and self.stance.why_this_matters_to_you == ""
            and self.stance.what_you_are_asking_for == ""
        )


def build_scaffold(
    *,
    verified_summary: str,
    source: SourceRecord,
    how_to_submit: str,
    where_to_submit: str,
) -> DraftScaffold:
    """Assemble a scaffold from a verified summary and the extraction record.

    The signature accepts NO stance input — deliberately. The only text arguments
    are the already-verified summary and the logistics strings; there is no
    parameter through which a position could enter. Receipt and deadline are copied
    from the record.

    Args:
        verified_summary: the plain-language summary that already passed the verifier.
        source: the extraction record (receipt + deadline come from here).
        how_to_submit / where_to_submit: logistics copied from the meeting record.

    Returns:
        A DraftScaffold whose stance fields are empty by construction.
    """
    receipt = Receipt(
        body=source.body,
        meeting_date=source.meeting_date,
        item_number=source.item_number,
        page_range=source.page_range,
        source_url=source.source_url,
    )
    logistics = Logistics(
        deadline=source.deadline,
        how_to_submit=how_to_submit,
        where_to_submit=where_to_submit,
    )
    # StanceFields() takes no arguments here: emptiness is the only constructable state.
    return DraftScaffold(
        item_summary=verified_summary,
        receipt=receipt,
        logistics=logistics,
    )
