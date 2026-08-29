"""Ventura adapter — PreviousVersions version trail (R2.3, R3).

For an in-horizon meeting, parse its PreviousVersions page into the full document
set: current Agenda/Minutes plus the ArchivedAgenda / ArchivedMinutes versions and
any supplemental/attachment entries. This is the ONLY place the amendment trail
appears — the index shows only the current document (verified).

Pure given the HTML string; the fetch is fetch.py, and the horizon gate (horizon.py)
runs BEFORE this is called so out-of-window meetings cost no fetch.

Each document is classified by role via classify.py (deterministic, no model).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from porchlight.adapters.ventura.classify import classify
from porchlight.adapters.ventura.models import DocumentRole
from porchlight.log import get_logger

log = get_logger("porchlight.adapters.ventura.previous_versions")

_VIEWFILE = re.compile(r"/AgendaCenter/ViewFile/[A-Za-z]+/_\d{8}-\d+")


@dataclass(frozen=True)
class DocumentRef:
    """A document discovered in the PreviousVersions trail, with its classified role.

    `document_id` (content hash) is assigned later, after the bytes are fetched;
    here we carry the URL, the human title used for classification, and the role.
    """

    url: str
    title: str
    role: DocumentRole


def parse_previous_versions(pv_html: str, base_url: str = "https://www.cityofventura.ca.gov") -> list[DocumentRef]:
    """Parse a PreviousVersions page into classified document refs.

    Never raises on a malformed anchor: a link that cannot be parsed is logged and
    skipped, never silently dropped in a way that hides a document.
    """
    soup = BeautifulSoup(pv_html, "html.parser")
    refs: list[DocumentRef] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        try:
            href = a["href"]
            if not _VIEWFILE.search(href):
                continue
            url = href if href.startswith("http") else base_url + href
            if url in seen:
                continue
            seen.add(url)
            title = a.get_text(" ", strip=True)
            role = classify(url, title)
            if role == DocumentRole.UNCLASSIFIED:
                # Surface, do not guess (R3.6).
                log.warning("pv_unclassified_document", url=url, title=title[:80])
            refs.append(DocumentRef(url=url, title=title, role=role))
        except Exception as e:  # noqa: BLE001 - log and continue
            log.error("pv_anchor_error", error=type(e).__name__)
            continue

    log.info("pv_parsed", documents=len(refs))
    return refs
