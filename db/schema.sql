-- Porch Light — ingestion schema (Spec 2).
--
-- Backend-agnostic DDL: runs on local docker-compose Postgres and on Aurora
-- Serverless v2 PostgreSQL via the RDS Data API (§33). Extensions (vector,
-- pg_trgm, unaccent) are bootstrapped separately (db/init/001-extensions.sql
-- locally; created once on Aurora at cluster setup, task 12).
--
-- Vocabulary (§35a): "agenda"/"document", never "packet".
-- Time (§2): timestamps are timestamptz; meeting-local time is carried explicitly.
-- Absence (§16b, never.md #3): status columns never encode "late/overdue/failed".

-- ---------------------------------------------------------------------------
-- bodies: the 21 Ventura public bodies (mirrors adapters/ventura/registry.py).
-- Static-ish; a rot point with a verification date (§11).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bodies (
    body_id      TEXT PRIMARY KEY,
    name_en      TEXT NOT NULL,
    category     TEXT NOT NULL CHECK (category IN ('legislative', 'advisory'))
);

-- ---------------------------------------------------------------------------
-- meetings: one dated convening of a body.
-- meeting_date is authoritative from source (never posting order / file name).
-- start_time_local is the parsed meeting start (NULL when unparseable → the
-- surfacing rule falls back to end-of-day and logs it, Spec 1 R5.4).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meetings (
    meeting_id        TEXT PRIMARY KEY,       -- city's stable id from the URL segment
    body_id           TEXT NOT NULL REFERENCES bodies(body_id),
    meeting_date      DATE NOT NULL,
    meeting_type      TEXT NOT NULL,          -- regular/special/adjourned/closed_session/unknown
    start_time_local  TIMESTAMPTZ,            -- meeting start in city local time, or NULL
    cancelled         BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings (meeting_date);
CREATE INDEX IF NOT EXISTS idx_meetings_body ON meetings (body_id);

-- ---------------------------------------------------------------------------
-- documents: one file attached to a meeting, keyed by content hash (§7 R3.7).
-- status drives the in-process work list + crash-restart resume (Spec 2 R4):
--   pending → in_flight → done | parked (transient, auto-retry) | permanent_fail
-- document_id is the content hash, so an identical re-post is idempotent.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,         -- 'doc_sha256_<hex>' content hash
    meeting_id      TEXT NOT NULL REFERENCES meetings(meeting_id),
    url             TEXT NOT NULL,            -- permitted-host URL only (§34)
    role            TEXT NOT NULL,            -- agenda/amended_agenda/supplemental/cancellation/spanish_edition/minutes/unclassified
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','in_flight','done','parked','permanent_fail')),
    last_modified   TEXT,                     -- for conditional GET (§7 R7.3)
    etag            TEXT,
    fail_reason     TEXT,                     -- attached on parked/permanent_fail; never rendered as "late/overdue"
    attempts        INT NOT NULL DEFAULT 0,   -- L1 cap = 2 (§16a)
    first_seen_run  TEXT,                     -- run_id that first recorded it
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status);
CREATE INDEX IF NOT EXISTS idx_documents_meeting ON documents (meeting_id);

-- ---------------------------------------------------------------------------
-- items: populated by Spec 3 (extraction). Declared here so the schema is whole
-- and the vector index exists from the start (§18b#7). Embeddings are pgvector.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS items (
    item_id       TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES documents(document_id),
    item_number   TEXT,                       -- copied from source, never generated (never.md #1)
    page_start    INT,
    page_end      INT,
    embedding     vector(1024)                -- dim finalized at Spec 3/4; placeholder now
);
CREATE INDEX IF NOT EXISTS idx_items_document ON items (document_id);
-- Vector index created at Spec 4 once the embedding model/dim is fixed; a stub
-- note rather than an index on a possibly-wrong dimension.

-- ---------------------------------------------------------------------------
-- body_status: per-body last-read + quarantine (§16a L4, §16b, §7 R7.4).
-- Per-body last-read ONLY; a single global last-read is banned (R7.4).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS body_status (
    body_id             TEXT PRIMARY KEY REFERENCES bodies(body_id),
    last_read_at        TIMESTAMPTZ,          -- last SUCCESSFUL read of this body
    consecutive_fails   INT NOT NULL DEFAULT 0,
    quarantined         BOOLEAN NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- readlog: one row per run (the data Spec 6 renders as the public reading log).
-- counts are honest and separate; "skipped" is unchanged-not-failed.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS readlog (
    run_id            TEXT PRIMARY KEY,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running','ok','interrupted','timed_out','circuit_broken','budget_halted')),
    read_count        INT NOT NULL DEFAULT 0,
    skipped_count     INT NOT NULL DEFAULT 0,  -- unchanged (304)
    failed_count      INT NOT NULL DEFAULT 0,
    quarantined_count INT NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(10,4) NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- spend_ledger: append-only model/API spend (§16a L5, §18b).
-- NOT infrastructure: Aurora's ~$43/mo fixed compute is tracked in §13, not here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spend_ledger (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    component   TEXT NOT NULL,                -- 'ingestion' | 'search' (sub-budgets of T15)
    cost_usd    NUMERIC(10,4) NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_component_ts ON spend_ledger (component, ts);

-- ---------------------------------------------------------------------------
-- run_lock: the run mutex (§20). A DB row, not an in-memory flag, so it survives
-- process death. heartbeat_at is capped at acquired_at + T11 by the app so a
-- stuck-but-alive run's lock still expires at T12 (the §20 side-door fix).
-- Single-row table (lock_name is the key so there is exactly one lock).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_lock (
    lock_name     TEXT PRIMARY KEY DEFAULT 'ingestion',
    run_id        TEXT NOT NULL,
    acquired_at   TIMESTAMPTZ NOT NULL,
    heartbeat_at  TIMESTAMPTZ NOT NULL,
    ttl_seconds   INT NOT NULL
);
