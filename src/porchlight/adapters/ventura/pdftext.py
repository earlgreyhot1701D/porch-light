"""Ventura adapter — per-page PDF text extraction (Spec 3 R2, root-cause task).

Pure function over bytes, no I/O, no network, no model. Extracts the text layer of
each page from already-fetched PDF bytes, so ingestion can persist per-page text
from the SAME bytes it hashed (no re-fetch, §40b). Text is returned verbatim,
artifacts intact (the repair pass in verify/entities.py reads THROUGH artifacts;
source text is never mutated).

A page with no extractable text layer (image-only scan) yields "" for that page —
the caller marks the document unreadable rather than guessing (R1.6, never.md #1).
"""

from __future__ import annotations

from io import BytesIO


def extract_pages(pdf_bytes: bytes) -> list[str]:
    """Return the text of each page, in order (index 0 = page 1).

    Never raises: a malformed PDF or a page with no text layer yields an empty
    list or "" pages respectively, which the caller treats as unreadable rather
    than fabricating content.
    """
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        return []
