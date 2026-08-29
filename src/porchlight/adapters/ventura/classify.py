"""Ventura adapter — deterministic document role classification (R3).

Pure function, no I/O, no model (§model-authority: document role is code, never
model-decided). Keyed on the REAL string signals Ventura uses, verified against
the live AgendaCenter index and a PreviousVersions page:

    "**CANCELLED** Appointments Recommendation Committee Special ..."   -> cancellation
    "10 DE FEBRERO DE 2026 AGENDA DEL CONCEJO MUNICIPAL"               -> spanish_edition
    "Amended Arts and Culture Commission Regular Meeting (01/08/2026)" -> amended_agenda
    "Arts & Culture Commission Supplemental Packet (06.11.2026)"       -> supplemental
    ViewFile/Minutes/, ViewFile/ArchivedMinutes/                       -> minutes
    ViewFile/Agenda/, ViewFile/ArchivedAgenda/ (default)              -> agenda

When no signal fires confidently, the role is UNCLASSIFIED — a first-class
outcome that gets surfaced for review, never a guess (R3.6, never.md #1).

Note on "packet" (§35a): Ventura's OWN official term for added material is
"Supplemental Packet" (verified verbatim on the site). We preserve the city's
term when matching its text — misquoting the source would be its own error — but
our role name is `supplemental` and our user-facing copy says "new material
added (official term: supplemental packet)" per voice.md. Matching the city's
literal string is not the same as us calling Ventura's agendas "packets."
"""

from __future__ import annotations

import re

from porchlight.adapters.ventura.models import DocumentRole

# --- URL doc-type segment -> baseline role ---
# The ViewFile path segment is the most reliable signal and comes first.
_URL_TYPE = re.compile(r"/ViewFile/([A-Za-z]+)/", re.IGNORECASE)

# --- Cancellation: Ventura prefixes the row label, e.g. "**CANCELLED** ...". ---
_CANCELLED = re.compile(r"\bcancell?ed\b", re.IGNORECASE)

# --- Amended: "Amended <body> Meeting (mm/dd/yyyy)". ---
_AMENDED = re.compile(r"\bamended\b", re.IGNORECASE)

# --- Supplemental: "Supplemental Packet", "Public Hearing Notices/Supplemental Packet". ---
_SUPPLEMENTAL = re.compile(r"\bsupplement", re.IGNORECASE)

# --- Spanish edition: Spanish-language title markers. Ventura publishes some
# agendas in Spanish with titles like "... AGENDA DEL CONCEJO MUNICIPAL" and
# Spanish month names / "DE". We require a Spanish month or a clear Spanish
# agenda phrase so an English title with a stray Spanish word does not trip it. ---
_SPANISH_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_SPANISH_PHRASE = re.compile(
    r"\bagenda del\b|\bconcejo municipal\b|\breuni[oó]n\b", re.IGNORECASE
)


def _is_spanish(title: str) -> bool:
    low = title.lower()
    if _SPANISH_PHRASE.search(low):
        return True
    # A Spanish month name plus "de" (date phrasing "10 DE FEBRERO DE 2026").
    if " de " in f" {low} " and any(m in low for m in _SPANISH_MONTHS):
        return True
    return False


def classify(url: str, title: str) -> DocumentRole:
    """Classify one document by role from deterministic signals.

    Args:
        url: the document's ViewFile URL (its path segment is the primary signal).
        title: the human-readable row/link label as rendered by the city.

    Returns:
        A DocumentRole. UNCLASSIFIED when nothing fires confidently — never a guess.

    Never raises: any unexpected input degrades to UNCLASSIFIED.
    """
    try:
        title = title or ""
        url = url or ""

        # 1. Cancellation wins over everything: a cancelled meeting's document is
        #    not new agenda content regardless of its ViewFile type (R3.2).
        if _CANCELLED.search(title):
            return DocumentRole.CANCELLATION

        # 2. Spanish edition: detected from the title, links to the same meeting
        #    as its English counterpart upstream (R3.4). Checked before agenda/
        #    amended so a Spanish agenda is tagged spanish_edition, not agenda.
        if _is_spanish(title):
            return DocumentRole.SPANISH_EDITION

        # 3. URL type segment: the reliable structural signal.
        m = _URL_TYPE.search(url)
        seg = m.group(1).lower() if m else ""

        if seg in ("minutes", "archivedminutes"):
            return DocumentRole.MINUTES

        # 4. Supplemental: added material (Ventura's official term "Supplemental
        #    Packet"), distinct from a full replacement agenda (R3.3).
        if _SUPPLEMENTAL.search(title):
            return DocumentRole.SUPPLEMENTAL

        # 5. Amended: a newer full version of the agenda (R3.3).
        if _AMENDED.search(title):
            return DocumentRole.AMENDED_AGENDA

        # 6. Agenda: the default for agenda/archivedagenda documents.
        if seg in ("agenda", "archivedagenda"):
            return DocumentRole.AGENDA

        # 7. Nothing fired confidently.
        return DocumentRole.UNCLASSIFIED
    except Exception:
        # Never raise from a classifier; an unexpected input is unclassified,
        # surfaced for review, never a crash mid-run.
        return DocumentRole.UNCLASSIFIED
