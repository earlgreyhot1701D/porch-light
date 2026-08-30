-- Migration 003 — item_rewrites (Spec 3 W3)
--
-- Additive, idempotent. Stores verified rewrites + per-language verify outcome.
-- NULL es_text with es_verified FALSE is the honest ES fallback (never.md #7);
-- an unverified rewrite is NEVER stored.

CREATE TABLE IF NOT EXISTS item_rewrites (
    item_id         TEXT PRIMARY KEY REFERENCES items(item_id),
    run_id          TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    en_text         TEXT NOT NULL,
    en_verified     BOOLEAN NOT NULL,
    en_attempts     INT NOT NULL,
    es_text         TEXT,
    es_verified     BOOLEAN NOT NULL,
    es_attempts     INT NOT NULL DEFAULT 0,
    note_en         TEXT NOT NULL DEFAULT '',
    es_absent_note  TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_item_rewrites_run ON item_rewrites (run_id);
