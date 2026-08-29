"""Property + example tests for the Ventura document classifier.

# Feature: 1-ventura-adapter, Property 1: classifier soundness

The classifier is an invisible-failure surface: a wrong role silently mis-files a
document. Property tests assert it never crashes and never returns a role whose
signal is absent; example tests pin the REAL Ventura strings verified on the live
site.
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from porchlight.adapters.ventura.classify import classify
from porchlight.adapters.ventura.models import DocumentRole


# --- Example tests: real strings verified against the live AgendaCenter ---

def test_real_cancellation():
    assert classify(
        "/AgendaCenter/ViewFile/Agenda/_01012026-1",
        "**CANCELLED** Appointments Recommendation Committee Special Meeting",
    ) == DocumentRole.CANCELLATION


def test_real_spanish_edition():
    assert classify(
        "/AgendaCenter/ViewFile/Agenda/_02102026-1",
        "10 DE FEBRERO DE 2026 AGENDA DEL CONCEJO MUNICIPAL",
    ) == DocumentRole.SPANISH_EDITION


def test_real_amended():
    assert classify(
        "/AgendaCenter/ViewFile/ArchivedAgenda/_01082026-1",
        "Amended Arts and Culture Commission Regular Meeting (01/08/2026)",
    ) == DocumentRole.AMENDED_AGENDA


def test_real_supplemental():
    assert classify(
        "/AgendaCenter/ViewFile/Agenda/_06112026-1",
        "Arts & Culture Commission Supplemental Packet (06.11.2026)",
    ) == DocumentRole.SUPPLEMENTAL


def test_real_agenda():
    assert classify(
        "/AgendaCenter/ViewFile/Agenda/_08252026-3685",
        "City Council Regular Meeting",
    ) == DocumentRole.AGENDA


def test_real_minutes():
    assert classify(
        "/AgendaCenter/ViewFile/Minutes/_02102026-3569",
        "City Council Regular Meeting",
    ) == DocumentRole.MINUTES


def test_archived_minutes_is_minutes():
    assert classify(
        "/AgendaCenter/ViewFile/ArchivedMinutes/_02102026-3802",
        "City Council Regular Meeting",
    ) == DocumentRole.MINUTES


def test_unknown_url_unknown_title_is_unclassified():
    assert classify("/something/else", "Untitled") == DocumentRole.UNCLASSIFIED


# --- Property tests ---

@given(url=st.text(max_size=200), title=st.text(max_size=200))
def test_never_crashes_and_returns_valid_role(url, title):
    """Property: any input returns a valid DocumentRole, never an exception."""
    role = classify(url, title)
    assert isinstance(role, DocumentRole)


@given(title=st.text(max_size=200))
def test_no_role_without_its_signal(title):
    """Property: a role is only returned when its signal is present.

    Specifically: if the title carries no cancellation/spanish/amended/supplemental
    marker AND the URL has no recognizable ViewFile type, the result is
    UNCLASSIFIED — the classifier never invents a role from nothing.
    """
    role = classify("/no/viewfile/segment/here", title)
    low = title.lower()
    has_cancel = "cancel" in low
    has_amend = "amend" in low
    has_supp = "supplement" in low
    has_spanish = any(
        m in low for m in ("enero", "febrero", "marzo", "abril", "mayo", "junio",
                            "julio", "agosto", "septiembre", "octubre", "noviembre",
                            "diciembre")
    ) or ("agenda del" in low) or ("concejo municipal" in low)
    if not (has_cancel or has_amend or has_supp or has_spanish):
        assert role == DocumentRole.UNCLASSIFIED
