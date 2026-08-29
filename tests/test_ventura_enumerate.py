"""Tests for the Ventura index parser and PreviousVersions parser.

# Feature: 1-ventura-adapter, Property 3: index parser

Working-rigor tests run against real saved fixtures (the live combined index and
one PreviousVersions page). Property tests assert the parser never crashes and
never emits a meeting without a valid date and at least one document URL.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from hypothesis import given, strategies as st

from porchlight.adapters.ventura.enumerate import enumerate_meetings
from porchlight.adapters.ventura.previous_versions import parse_previous_versions
from porchlight.adapters.ventura.models import DocumentRole

FIX = Path(__file__).parent / "fixtures" / "ventura"


def _index_html() -> str:
    return (FIX / "agenda_center_index.html").read_text(encoding="utf-8")


def _pv_html() -> str:
    return (FIX / "previous_versions_3569.html").read_text(encoding="utf-8")


# --- Working rigor against real fixtures ---

def test_enumerates_real_index():
    stubs = enumerate_meetings(_index_html())
    # Verified: 129 meetings in the index at capture time.
    assert len(stubs) >= 120, f"expected ~129 meetings, got {len(stubs)}"
    # Every stub has a valid date and at least one document URL.
    for s in stubs:
        assert isinstance(s.meeting_date, date)
        assert s.document_urls, f"meeting {s.meeting_id} has no document URLs"


def test_index_attributes_city_council():
    stubs = enumerate_meetings(_index_html())
    cc = [s for s in stubs if s.body_id == "city_council"]
    # City Council was the largest body (30 meetings at capture).
    assert len(cc) >= 20, f"expected many City Council meetings, got {len(cc)}"


def test_known_meeting_present_with_correct_date():
    stubs = enumerate_meetings(_index_html())
    m = next((s for s in stubs if s.meeting_id == "3569"), None)
    assert m is not None, "meeting 3569 should be in the index"
    assert m.meeting_date == date(2026, 2, 10)
    assert m.previous_versions_url is not None


def test_previous_versions_finds_amendment_trail():
    refs = parse_previous_versions(_pv_html())
    # Verified: this PV page lists multiple ArchivedAgenda versions + Minutes.
    assert len(refs) >= 5, f"expected several documents, got {len(refs)}"
    roles = {r.role for r in refs}
    # It contains agenda-type and minutes-type documents.
    assert DocumentRole.AGENDA in roles or DocumentRole.AMENDED_AGENDA in roles
    assert DocumentRole.MINUTES in roles


# --- Property: parser robustness ---

@given(html=st.text(max_size=2000))
def test_enumerate_never_crashes(html):
    """Property: arbitrary/malformed HTML never raises; result is a list."""
    result = enumerate_meetings(html)
    assert isinstance(result, list)


@given(html=st.text(max_size=2000))
def test_pv_never_crashes(html):
    """Property: arbitrary/malformed HTML never raises; result is a list."""
    result = parse_previous_versions(html)
    assert isinstance(result, list)


def test_emitted_meetings_always_have_date_and_docs():
    """Property-ish invariant on the real fixture: no meeting is emitted without a
    date and at least one document URL (a partial row is skipped, not half-emitted)."""
    for s in enumerate_meetings(_index_html()):
        assert s.meeting_date is not None
        assert len(s.document_urls) >= 1
