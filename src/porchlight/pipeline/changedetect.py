"""Porch Light — change detection and idempotent document recording (Spec 2 R3).

Conditional GET first: a 304 means unchanged → mark done, write nothing new
(the common case on most runs). On 200, the content hash (Spec 1) is the document
id; an upsert keyed on that id means identical bytes never create a second row and
never re-do downstream work. This is what makes a re-run and a crash-restart safe
(pass gates 1 and 2).

The document row and its status are written in the SAME transaction path as the
work that produced them (R3.3), so a restart reads a coherent state and resumes.
"""

from __future__ import annotations

from dataclasses import dataclass

from porchlight.adapters.ventura import fetch as vfetch
from porchlight.adapters.ventura.hash import document_id
from porchlight.adapters.ventura.pdftext import extract_pages
from porchlight.log import get_logger

log = get_logger("porchlight.pipeline.changedetect")


@dataclass(frozen=True)
class RecordOutcome:
    document_id: str | None
    changed: bool     # True if new bytes were recorded this run WITH usable text
    unchanged: bool   # True if a 304 / identical-hash skip
    url: str
    failed: bool = False          # True if fetched-but-extracted-nothing (not 'done')
    fail_reason: str | None = None  # attached on failed; e.g. 'no_text_layer'


def _has_usable_text(pages: list[str]) -> bool:
    """True iff extraction produced at least one page with non-blank text.

    An empty list (malformed/unparseable PDF) or all-blank pages (image-only scan
    with no text layer) is NOT usable text — the document must not reach 'done'.
    """
    return any((p or "").strip() for p in pages)


def record_document(backend, url: str, meeting_id: str, role: str, run_id: str) -> RecordOutcome:
    """Fetch (conditionally), hash, and upsert a document idempotently.

    Returns a RecordOutcome describing whether bytes were newly recorded, skipped
    as unchanged, or (on the caller's side) failed. Never raises for a normal
    not-modified; fetch errors propagate to the caller's retry budget.
    """
    # Prior conditional-GET validators, if we have this document already.
    prior = backend.query(
        "SELECT document_id, last_modified, etag FROM documents WHERE url = %s "
        "ORDER BY updated_at DESC LIMIT 1",
        [url],
    )
    if_mod = prior.rows[0]["last_modified"] if prior.rows else None
    if_etag = prior.rows[0]["etag"] if prior.rows else None

    result = vfetch.fetch(url, if_modified_since=if_mod, if_none_match=if_etag)

    if result.status == 304 or result.body is None:
        # Unchanged: nothing to write. Mark the existing doc done if present.
        if prior.rows:
            backend.execute(
                "UPDATE documents SET status = 'done', updated_at = now() WHERE document_id = %s",
                [prior.rows[0]["document_id"]],
            )
        log.info("doc_unchanged", url=url, meeting_id=meeting_id)
        return RecordOutcome(
            document_id=prior.rows[0]["document_id"] if prior.rows else None,
            changed=False, unchanged=True, url=url,
        )

    doc_id = document_id(result.body)

    # Idempotent upsert keyed on the content hash. If this id already exists, the
    # bytes are identical → no new row, no downstream re-work (R3.2).
    existing = backend.query("SELECT document_id FROM documents WHERE document_id = %s", [doc_id])
    if existing.rows:
        backend.execute(
            "UPDATE documents SET status = 'done', last_modified = %s, etag = %s, updated_at = now() "
            "WHERE document_id = %s",
            [result.last_modified, result.etag, doc_id],
        )
        log.info("doc_hash_seen", url=url, document_id=doc_id)
        return RecordOutcome(document_id=doc_id, changed=False, unchanged=True, url=url)

    # Extract FIRST, then decide status. Zero pages must never be indistinguishable
    # from success: 'done' is reached only when extraction produced usable text.
    # `pdftext.extract_pages` never raises — it returns [] for an unparseable PDF and
    # "" for a page with no text layer (image-only scan). Its docstring says the
    # caller marks such a document unreadable; THIS is that caller doing so (the bug
    # was that it did not — it wrote 'done' before extracting and no-oped on []).
    pages = extract_pages(result.body)

    if not _has_usable_text(pages):
        # No usable text: record the document, but NOT as 'done'. `no_text_layer`
        # classifies as PERMANENT (image-only scan needs OCR — a human/v2 path, not
        # an hourly retry that will fail identically). Stored with a fail_reason and
        # attempts=1 so it is distinguishable from success and from an untried doc.
        # fail_reason is diagnostic only; never rendered as "late/overdue" (§16b).
        fail_reason = "no_text_layer"
        backend.execute(
            "INSERT INTO documents (document_id, meeting_id, url, role, status, last_modified, "
            "etag, fail_reason, attempts, first_seen_run) "
            "VALUES (%s, %s, %s, %s, 'permanent_fail', %s, %s, %s, 1, %s)",
            [doc_id, meeting_id, url, role, result.last_modified, result.etag, fail_reason, run_id],
        )
        log.warning("doc_unreadable", url=url, document_id=doc_id, meeting_id=meeting_id,
                    pages=len(pages), fail_reason=fail_reason)
        return RecordOutcome(document_id=doc_id, changed=False, unchanged=False, url=url,
                             failed=True, fail_reason=fail_reason)

    # Usable text: record the document as 'done' and persist per-page text from the
    # SAME fetched bytes (no re-fetch, §40b). Idempotent on the content-hash id.
    backend.execute(
        "INSERT INTO documents (document_id, meeting_id, url, role, status, last_modified, etag, "
        "first_seen_run) VALUES (%s, %s, %s, %s, 'done', %s, %s, %s)",
        [doc_id, meeting_id, url, role, result.last_modified, result.etag, run_id],
    )
    for page_number, page_text in enumerate(pages, start=1):
        backend.execute(
            "INSERT INTO document_pages (document_id, page_number, text) VALUES (%s, %s, %s) "
            "ON CONFLICT (document_id, page_number) DO UPDATE SET text = EXCLUDED.text",
            [doc_id, page_number, page_text],
        )

    log.info("doc_recorded", url=url, document_id=doc_id, meeting_id=meeting_id, pages=len(pages))
    return RecordOutcome(document_id=doc_id, changed=True, unchanged=False, url=url)
