"""Ventura adapter — content-hash document ids (R3.7).

Pure function of document bytes. Identical bytes always produce the same id, so a
re-posted identical file is idempotent (§7 idempotency guarantee) and change
detection is deterministic.

SHA-256 is used because collision resistance matters here: two genuinely
different agendas must never hash to the same id, or one would silently overwrite
the other in storage.
"""

from __future__ import annotations

import hashlib

# Prefix makes the id self-describing in logs and storage, and versions the
# hashing scheme so a future algorithm change is distinguishable rather than
# silently colliding with old ids.
_ID_PREFIX = "doc_sha256_"


def document_id(content: bytes) -> str:
    """Return a stable content-hash id for a document.

    Args:
        content: the raw document bytes.

    Returns:
        'doc_sha256_<64 hex chars>'. Same bytes -> same id, always.
    """
    digest = hashlib.sha256(content).hexdigest()
    return f"{_ID_PREFIX}{digest}"
