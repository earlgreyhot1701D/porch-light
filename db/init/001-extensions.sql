-- Porch Light — local dev bootstrap.
-- Runs once on first container boot. Schema migrations live in db/migrations
-- and are applied by the app, not here; this file only guarantees that the
-- extensions the schema depends on exist.

CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector, item embeddings (§5)
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- trigram support for lexical search
CREATE EXTENSION IF NOT EXISTS unaccent;    -- accent-insensitive Spanish matching (§8)

-- Sanity marker so `docker compose logs db` shows this ran.
DO $$ BEGIN RAISE NOTICE 'Porch Light: extensions ready (vector, pg_trgm, unaccent)'; END $$;
