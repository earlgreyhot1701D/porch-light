"""The extractor's tool bodies, bound to one invocation's stored page text (R1).

The allowlisted tools (`tools.ALLOWED_TOOLS`) need two things a pure function
cannot hold across a model loop: the document's page text (to serve ranges) and a
place to collect the items the model records. `ExtractParseSession` is that per-
invocation state, and `build_tools` produces the four Strands `@tool` callables
bound to it. One session per document; nothing is shared across invocations.

Containment (R1.2, never.md #9): every tool operates ONLY on the page text handed
to the session at construction. None fetches, none touches the network, none reads
another document. `get_document_pages` serves ranges from in-memory text; the
model reads text it was given, it does not go find more. This is why the no-egress
runtime asks nothing the work needs — the tools cannot reach out even in principle.

Source fidelity (R1.5) stays in `tools.validate_items`: `record_items` collects
what the model proposes; the entrypoint validates the collection against the source
before anything is persisted. The tool does not self-certify.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from porchlight.agents.extractor.tools import ExtractedItem


@dataclass(frozen=True)
class RecordedOmission:
    """A numbered item the model deliberately did NOT record as an item, with its
    reason. The extractor MUST NOT silently drop a numbered item (relevance is the
    watcher's job, with a receipt — never the extractor's, decisions §46). If the
    model chooses to omit one, it returns the omission here so the pipeline logs it
    and nothing disappears without a trace."""

    item_number: str
    reason: str


@dataclass
class ExtractParseSession:
    """One document's page text + the items (and omissions) the model records.

    `pages` is 1-based conceptually (pages[0] is page 1). `recorded` accumulates the
    model's proposed items in call order; the entrypoint validates them after the
    run. `omissions` accumulates any numbered item the model deliberately did not
    record, with its reason — a silent drop is a failure, an explicit omission is
    honest (decisions §46).
    """

    pages: list[str]
    recorded: list[ExtractedItem] = field(default_factory=list)
    omissions: list[RecordedOmission] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def full_text(self) -> str:
        """All pages joined — the source text validation checks item numbers against."""
        return "\n".join(self.pages)


def build_tools(session: ExtractParseSession) -> list:
    """Produce the allowlisted tools bound to `session`.

    Returned as Strands `@tool` callables. Imported lazily so this module (and the
    session dataclass) needs no SDK in a unit-test environment; the tools are tested
    through the session's observable state, not through the SDK.
    """
    from strands import tool

    @tool
    def find_listing_pages() -> str:
        """List the page numbers of this document and a short preview of each, so you
        can find where the agenda items are. Returns one line per page: 'page N: <preview>'."""
        lines = []
        for i, text in enumerate(session.pages, start=1):
            preview = " ".join((text or "").split())[:120]
            lines.append(f"page {i}: {preview}")
        return "\n".join(lines) if lines else "(document has no pages)"

    @tool
    def get_document_pages(first_page: int, last_page: int) -> str:
        """Return the verbatim text of pages first_page..last_page (1-based, inclusive)
        from THIS document. Use this to read an item's text before recording it. Pages
        outside the document are ignored; nothing is fetched."""
        if first_page < 1:
            first_page = 1
        if last_page > session.page_count:
            last_page = session.page_count
        if last_page < first_page:
            return "(no such page range)"
        chunks = []
        for n in range(first_page, last_page + 1):
            chunks.append(f"[page {n}]\n{session.pages[n - 1]}")
        return "\n\n".join(chunks)

    @tool
    def extract_items(note: str = "") -> str:
        """Signal that you are about to record the agenda items you found. Optionally
        pass a short note about how many items and where. This does not store anything;
        use record_items for each item."""
        return (
            "Ready. Call record_items once per agenda item with its item_number, "
            "first_page, last_page, and the item's verbatim text copied from the document."
        )

    @tool
    def record_items(item_number: str, first_page: int, last_page: int, text: str) -> str:
        """Record ONE agenda item. item_number and the page range MUST be copied from
        the document exactly, never invented. text is the item's verbatim text. Call
        once per item. Returns a running count of items recorded so far."""
        session.recorded.append(
            ExtractedItem(
                item_number=str(item_number).strip(),
                page_range=(int(first_page), int(last_page)),
                text=text or "",
            )
        )
        return f"recorded item {item_number!r}; {len(session.recorded)} item(s) so far"

    @tool
    def record_omission(item_number: str, reason: str) -> str:
        """Record a numbered agenda item you are deliberately NOT recording as an item,
        and WHY (for example a ceremonial 'Call to Order' or 'Roll Call'). You are NOT
        allowed to silently skip a numbered item — if you do not record it as an item,
        you MUST record it here with its number and reason. Deciding what matters is
        not your job; recording everything you found, is."""
        session.omissions.append(
            RecordedOmission(item_number=str(item_number).strip(), reason=reason or "")
        )
        return f"recorded omission of item {item_number!r}; {len(session.omissions)} omission(s) so far"

    return [find_listing_pages, get_document_pages, extract_items, record_items, record_omission]
