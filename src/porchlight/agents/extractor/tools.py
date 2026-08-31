"""Extractor tools + the two deterministic guards (R1, §3, §security).

The extractor is a model-driven loop, but its GUARANTEES are deterministic code
the model cannot influence, isolated here so they are unit-testable without the
runtime:

  1. **The tool allowlist** (`is_tool_allowed`) — the Strands-hook boundary. Only
     the five permitted tools run; anything else (a fetch, a shell, a write to
     another table) is a NEVER-trip, logged and blocked (never.md #9, R1.4). This is the
     first of two independent containment layers; the second is the runtime's
     no-egress networkMode (R1.2, enforced in the AgentCore config, not here).

  2. **Source fidelity** (`validate_items`) — the extractor's own
     invisible-failure surface (R1.5). An item whose number or page range is NOT
     present in the source text is rejected BEFORE storage. Item identity anchors
     to the source, never to model output (never.md #1). This is what task 4.2's
     property tests pin.

The tool BODIES here are thin and pure: they operate on document text/bytes passed
in, never fetch (R1.2 — no network, ever). Wiring to the real document store is a
Spec-2 storage-boundary call injected at the entrypoint; the tools themselves take
their inputs as arguments so they test offline and deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- The allowlist: the ONLY tools the extractor may call (R1.4, §security). ---
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "find_listing_pages",
        "get_document_pages",
        "extract_items",
        "record_items",
        # record_omission: the model records a numbered item it deliberately did NOT
        # record as an item, WITH a reason, so nothing is silently dropped (the
        # extractor must not decide relevance — decisions §46). No network, like the
        # rest; it only appends to the in-memory session.
        "record_omission",
    }
)


def is_tool_allowed(tool_name: str) -> bool:
    """True iff the tool is on the extractor's allowlist.

    Anything else — a fetch, a shell, a write outside the items table, an injected
    instruction's tool — is denied. The hook calls this before every tool
    invocation; a False result is a NEVER-trip (logged, blocked, R1.4).
    """
    return tool_name in ALLOWED_TOOLS


@dataclass(frozen=True)
class ExtractedItem:
    """One item the model proposed: number, page range, and text.

    All three must trace to the source (validate_items enforces it). `item_number`
    and `page_range` are the receipt-critical fields that must be COPIED from
    source, never generated (never.md #1).
    """

    item_number: str
    page_range: tuple[int, int]
    text: str


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of source-fidelity validation: which items stand, which are rejected."""

    accepted: tuple[ExtractedItem, ...]
    rejected: tuple[tuple[ExtractedItem, str], ...]
    """(item, reason) for each rejected item — reason is logged and surfaced."""


def _item_number_in_source(item_number: str, source_text: str) -> bool:
    """True iff the item number appears in the source text as a real token.

    Matches 'Item 7', 'ITEM 7.', '7.' at a line start, or a bare token '7' bounded
    by non-alphanumerics — the forms Ventura agendas use. Conservative: a number
    the source does not contain is rejected.
    """
    n = re.escape(item_number.strip())
    if not n:
        return False
    patterns = (
        rf"\bitem\s+{n}\b",
        rf"(?m)^\s*{n}\.",
        rf"(?<![0-9A-Za-z]){n}(?![0-9A-Za-z])",
    )
    return any(re.search(p, source_text, re.IGNORECASE) for p in patterns)


def validate_items(
    items: list[ExtractedItem],
    source_text: str,
    document_page_count: int,
) -> ValidationResult:
    """Reject any item whose number or page range is not grounded in the source (R1.5).

    A page range must be within the document (1..page_count, first <= last). An
    item number must appear in the source text. Rejection is not an error — it is
    the guard working; the reason is returned for logging and surfacing.

    Never raises: a malformed item is rejected with a reason, not a crash.
    """
    accepted: list[ExtractedItem] = []
    rejected: list[tuple[ExtractedItem, str]] = []

    for item in items:
        try:
            first, last = item.page_range
        except (TypeError, ValueError):
            rejected.append((item, "malformed page_range"))
            continue
        if not (1 <= first <= last <= document_page_count):
            rejected.append(
                (item, f"page_range {item.page_range} outside document 1..{document_page_count}")
            )
            continue
        if not _item_number_in_source(item.item_number, source_text):
            rejected.append((item, f"item_number {item.item_number!r} not found in source"))
            continue
        accepted.append(item)

    return ValidationResult(accepted=tuple(accepted), rejected=tuple(rejected))
