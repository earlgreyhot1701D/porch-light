"""Ventura adapter — meeting enumeration from the combined AgendaCenter index (R2).

Parses the SINGLE combined /AgendaCenter served HTML (verified: 129 meetings, all
bodies, server-rendered) into meeting stubs, each attributed to a body. Does not
execute JavaScript and does not depend on per-body category pages (verified
inconsistent — some render server-side, some load via JS; the combined index is
reliable).

DOM structure verified on the live site:
- Meeting rows are `<... class="catAgendaRow">` elements, each containing a link
  to `/AgendaCenter/ViewFile/Agenda/_<MMDDYYYY>-<id>` (and often Minutes) plus a
  `PreviousVersions/_<MMDDYYYY>-<id>` link.
- Rows are grouped under body-name headers; a row's body is its nearest preceding
  heading (e.g. "City Council").
- The `_<MMDDYYYY>` URL segment gives the meeting date deterministically; it is
  cross-checked against the agenda PDF text downstream (R2.4, source wins).

This module is pure given the HTML string; the network fetch is fetch.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from porchlight.adapters.ventura.registry import body_for_name
from porchlight.log import get_logger

log = get_logger("porchlight.adapters.ventura.enumerate")

# /AgendaCenter/ViewFile/<Type>/_<MMDDYYYY>-<id>
_VIEWFILE = re.compile(r"/AgendaCenter/ViewFile/([A-Za-z]+)/_(\d{2})(\d{2})(\d{4})-(\d+)")
# /AgendaCenter/PreviousVersions/_<MMDDYYYY>-<id>
_PREVVERS = re.compile(r"/AgendaCenter/PreviousVersions/_(\d{2})(\d{2})(\d{4})-(\d+)")


@dataclass(frozen=True)
class MeetingStub:
    """A meeting as seen in the index, before the PreviousVersions trail is fetched."""

    meeting_id: str
    body_id: str | None  # None when the body name is unrecognized (surfaced, not dropped).
    body_name_raw: str | None
    meeting_date: date
    document_urls: tuple[str, ...]
    previous_versions_url: str | None


def _nearest_body_name(row) -> str | None:
    """The body name for a row = its nearest preceding heading that is not a date row."""
    for h in row.find_all_previous(["h2", "h3", "h4"]):
        t = h.get_text(strip=True)
        # Skip date-ish headers like "Aug25, 2026..." — real body names start with a
        # letter followed by more letters/spaces, not a 3-letter month + digit.
        if t and not re.match(r"^[A-Z][a-z]{2}\d", t):
            return t
    return None


def enumerate_meetings(index_html: str) -> list[MeetingStub]:
    """Parse the combined index HTML into meeting stubs.

    Never raises on a malformed row: a row that cannot be parsed is logged and
    skipped-with-surfacing (R2 honest states), never silently dropped in a way
    that hides it. A row with an unrecognized body name keeps body_id=None and is
    surfaced (registry rot point, R9.2).
    """
    soup = BeautifulSoup(index_html, "html.parser")
    stubs: list[MeetingStub] = []
    seen: set[str] = set()

    for row in soup.select(".catAgendaRow"):
        try:
            # Collect all ViewFile links and the PreviousVersions link in this row.
            # A row often links the same file twice (icon anchor + text anchor);
            # de-duplicate while preserving first-seen order so the document set
            # is not inflated downstream.
            viewfiles: list[str] = []
            seen_urls: set[str] = set()
            meeting_id = None
            meeting_date = None
            prev_url = None

            for a in row.find_all("a", href=True):
                href = a["href"]
                vm = _VIEWFILE.search(href)
                if vm:
                    if href not in seen_urls:
                        seen_urls.add(href)
                        viewfiles.append(href)
                    mid = vm.group(5)
                    mm, dd, yyyy = int(vm.group(2)), int(vm.group(3)), int(vm.group(4))
                    meeting_id = meeting_id or mid
                    meeting_date = meeting_date or date(yyyy, mm, dd)
                pm = _PREVVERS.search(href)
                if pm:
                    prev_url = href
                    meeting_id = meeting_id or pm.group(4)
                    if meeting_date is None:
                        meeting_date = date(int(pm.group(3)), int(pm.group(1)), int(pm.group(2)))

            if meeting_id is None or meeting_date is None:
                # Not a real meeting row (no meeting link). Skip quietly; these are
                # layout rows, not data we lost.
                continue

            if meeting_id in seen:
                continue
            seen.add(meeting_id)

            body_name = _nearest_body_name(row)
            body = body_for_name(body_name) if body_name else None
            if body_name and body is None:
                # Unrecognized body: surface for review, do not fabricate or drop.
                log.warning(
                    "enumerate_unknown_body",
                    body_name_raw=body_name,
                    meeting_id=meeting_id,
                )

            stubs.append(
                MeetingStub(
                    meeting_id=meeting_id,
                    body_id=body.body_id if body else None,
                    body_name_raw=body_name,
                    meeting_date=meeting_date,
                    document_urls=tuple(viewfiles),
                    previous_versions_url=prev_url,
                )
            )
        except Exception as e:  # noqa: BLE001 - log and continue; never fail the whole parse
            log.error("enumerate_row_error", error=type(e).__name__)
            continue

    log.info("enumerate_done", meetings=len(stubs))
    return stubs
