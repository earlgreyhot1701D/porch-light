-- Migration 004 — document_pages (Spec 3 R2, root-cause task)
--
-- Additive, idempotent. Per-page extracted text, persisted at ingestion from the
-- fetched bytes (no re-fetch, §40b). Per-page so item page ranges are recoverable.

CREATE TABLE IF NOT EXISTS document_pages (
    document_id   TEXT NOT NULL REFERENCES documents(document_id),
    page_number   INT NOT NULL,
    text          TEXT NOT NULL,
    PRIMARY KEY (document_id, page_number)
);
CREATE INDEX IF NOT EXISTS idx_document_pages_doc ON document_pages (document_id);
