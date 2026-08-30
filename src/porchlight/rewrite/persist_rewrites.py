"""Persist verified rewrites + per-language verify outcome (Spec 3 W3).

Writes one `item_rewrites` row per item, idempotently. Never stores an unverified
rewrite: on ES fallback `es_text` is NULL with `es_verified` FALSE and the honest
note; on EN fallback `en_text` holds the ORIGINAL staff text (what the reader is
shown) with `en_verified` FALSE. Receipt fields are NOT duplicated here — they
live on items/meetings and are attached from the record (containment), so a model
can never author a receipt into this table.
"""

from __future__ import annotations

from porchlight.log import get_logger
from porchlight.rewrite.pipeline import ItemRewriteResult

log = get_logger("porchlight.rewrite.persist")


def persist_item_rewrite(
    backend,
    item_id: str,
    run_id: str,
    model_id: str,
    result: ItemRewriteResult,
) -> None:
    """Upsert one item's rewrite outcome. Idempotent (a re-run overwrites cleanly).

    Enforces the never-fail-open invariant in what it STORES: `es_text` is written
    only when `es_verified`; otherwise NULL. An assertion guards against ever
    persisting an unverified rewrite as if verified.
    """
    # Guard: never persist an unverified rewrite as text-with-verified.
    es_text = result.es_text if result.es_verified else None
    assert not (es_text is not None and not result.es_verified), (
        "refusing to persist an unverified ES rewrite (never.md #7)"
    )

    backend.execute(
        "INSERT INTO item_rewrites "
        "(item_id, run_id, model_id, en_text, en_verified, en_attempts, "
        " es_text, es_verified, es_attempts, note_en, es_absent_note) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (item_id) DO UPDATE SET "
        "  run_id = EXCLUDED.run_id, model_id = EXCLUDED.model_id, "
        "  en_text = EXCLUDED.en_text, en_verified = EXCLUDED.en_verified, "
        "  en_attempts = EXCLUDED.en_attempts, es_text = EXCLUDED.es_text, "
        "  es_verified = EXCLUDED.es_verified, es_attempts = EXCLUDED.es_attempts, "
        "  note_en = EXCLUDED.note_en, es_absent_note = EXCLUDED.es_absent_note, "
        "  updated_at = now()",
        [
            item_id, run_id, model_id,
            result.en_text, result.en_verified, result.en_attempts,
            es_text, result.es_verified, result.es_attempts,
            result.note_en, result.es_absent_note,
        ],
    )
    log.info(
        "item_rewrite_persisted",
        item_id=item_id, run_id=run_id, model_id=model_id,
        en_verified=result.en_verified, es_verified=result.es_verified,
        en_attempts=result.en_attempts, es_attempts=result.es_attempts,
    )
