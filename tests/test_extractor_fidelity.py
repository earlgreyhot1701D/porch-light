"""Property + example tests for extractor source fidelity and the tool allowlist.

# Feature: 3-extraction, Property 3: extraction fidelity

The extractor is a model-driven loop, but two guarantees are deterministic and
must hold no matter what the model proposes:

  - **Source fidelity (R1.5):** an item whose number or page range is not grounded
    in the source is rejected before storage. A hallucinated item number or an
    out-of-range page span never reaches the store. This is an invisible-failure
    surface — a false accept ships a fabricated receipt.
  - **Tool allowlist (R1.4):** only the four permitted tools run; anything else is
    a blocked NEVER-trip. An injected "fetch this URL" is denied.
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from porchlight.agents.extractor.entrypoint import enforce_tool_allowlist
from porchlight.agents.extractor.tools import (
    ALLOWED_TOOLS,
    ExtractedItem,
    is_tool_allowed,
    validate_items,
)

_SOURCE = (
    "AGENDA\n"
    "Item 5. Approval of the minutes.\n"
    "Item 6. Consideration of a $1.2 million grant. (pages 4-5)\n"
    "7. Public hearing on the Main Street rezoning.\n"
)
_PAGE_COUNT = 12


class _Log:
    """Minimal log stub capturing NEVER-trip warnings."""

    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def warning(self, event: str, **kw) -> None:
        self.warnings.append((event, kw))


# --- Source fidelity: accept grounded, reject ungrounded ---

def test_accepts_items_grounded_in_source():
    items = [
        ExtractedItem("5", (1, 2), "minutes"),
        ExtractedItem("6", (4, 5), "grant"),
        ExtractedItem("7", (6, 7), "rezoning"),
    ]
    result = validate_items(items, _SOURCE, _PAGE_COUNT)
    assert len(result.accepted) == 3
    assert result.rejected == ()


def test_rejects_item_number_absent_from_source():
    items = [ExtractedItem("99", (1, 2), "invented item")]
    result = validate_items(items, _SOURCE, _PAGE_COUNT)
    assert result.accepted == ()
    assert len(result.rejected) == 1
    assert "not found in source" in result.rejected[0][1]


def test_rejects_page_range_outside_document():
    items = [ExtractedItem("6", (11, 20), "grant")]  # 20 > 12
    result = validate_items(items, _SOURCE, _PAGE_COUNT)
    assert result.accepted == ()
    assert "outside document" in result.rejected[0][1]


def test_rejects_inverted_page_range():
    items = [ExtractedItem("6", (5, 4), "grant")]  # first > last
    result = validate_items(items, _SOURCE, _PAGE_COUNT)
    assert result.accepted == ()


# --- Property: no ungrounded item ever survives validation ---

@given(
    item_number=st.integers(min_value=100, max_value=9999).map(str),
    first=st.integers(min_value=1, max_value=12),
    last=st.integers(min_value=1, max_value=12),
)
def test_property_ungrounded_item_number_never_accepted(item_number, first, last):
    """An item number absent from the source is never accepted, regardless of pages.

    Item numbers 100-9999 do not appear in _SOURCE, so every such item must be
    rejected even when its page range is otherwise valid.
    """
    lo, hi = min(first, last), max(first, last)
    items = [ExtractedItem(item_number, (lo, hi), "text")]
    result = validate_items(items, _SOURCE, _PAGE_COUNT)
    assert result.accepted == ()


@given(
    first=st.integers(min_value=-50, max_value=200),
    last=st.integers(min_value=-50, max_value=200),
)
def test_property_out_of_bounds_page_range_never_accepted(first, last):
    """A page range not fully within 1..page_count is never accepted (item # is valid)."""
    items = [ExtractedItem("6", (first, last), "grant")]
    result = validate_items(items, _SOURCE, _PAGE_COUNT)
    if 1 <= first <= last <= _PAGE_COUNT:
        assert len(result.accepted) == 1
    else:
        assert result.accepted == ()


# --- Tool allowlist ---

def test_allowlist_permits_only_the_four_tools():
    assert ALLOWED_TOOLS == {
        "find_listing_pages",
        "get_document_pages",
        "extract_items",
        "record_items",
    }
    for name in ALLOWED_TOOLS:
        assert is_tool_allowed(name)


def test_allowlist_blocks_injected_fetch_as_never_trip():
    log = _Log()
    assert enforce_tool_allowlist("http_get", log) is False
    assert log.warnings and log.warnings[0][0] == "never_trip_tool_blocked"
    assert log.warnings[0][1]["tool_name"] == "http_get"


@given(st.text(min_size=1, max_size=40).filter(lambda s: s not in ALLOWED_TOOLS))
def test_property_any_non_allowlisted_tool_is_blocked(tool_name):
    """Any tool name not on the allowlist is denied (fail closed)."""
    log = _Log()
    assert enforce_tool_allowlist(tool_name, log) is False
