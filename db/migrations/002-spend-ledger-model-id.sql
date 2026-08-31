-- Migration 002 — spend_ledger.model_id (Spec 3 R9.1, §27)
--
-- Additive and idempotent. The spend_ledger table already exists live (Spec 2),
-- so CREATE TABLE IF NOT EXISTS in schema.sql will not add this column to the
-- existing table; this ALTER does. Nullable, so existing ingestion/API rows
-- (which have no model) are unaffected — not a breaking change to the Spec 2 path.
--
-- Model spend must be attributable per model id for the §27 cost-per-agenda
-- comparison, and the model id appears in every structured log event (§27).

-- Rollback (safe; model_id is nullable/additive, no data depends on it):
--   DROP INDEX IF EXISTS idx_ledger_model_ts;
--   ALTER TABLE spend_ledger DROP COLUMN IF EXISTS model_id;
-- Applied to Aurora porchlight-dev 2026-08-31, in order 002->003->004, each run
-- twice with no error (idempotency verified live).

ALTER TABLE spend_ledger ADD COLUMN IF NOT EXISTS model_id TEXT;
CREATE INDEX IF NOT EXISTS idx_ledger_model_ts ON spend_ledger (model_id, ts);
