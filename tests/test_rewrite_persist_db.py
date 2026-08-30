"""DB-backed test for W3: persist verified rewrites + per-language outcome.

Needs a real Postgres. Skips cleanly when DATABASE_URL is unset (Spec 0 skip-vs-fail
discipline). Verifies: an item's rewrite round-trips; an ES-fallback stores NULL
es_text with the honest note; receipt fields are NOT in this table (they come from
the record). No live model call — the ItemRewriteResult is constructed directly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL unset: no database for rewrite-persist tests.",
)

from db import data_api  # noqa: E402
from porchlight.rewrite.persist_rewrites import persist_item_rewrite  # noqa: E402
from porchlight.rewrite.pipeline import ItemRewriteResult  # noqa: E402
from porchlight.verify.models import SourceRecord  # noqa: E402

_SRC = SourceRecord(
    body="city_council", meeting_date="2026-08-25", item_number="6",
    page_range=(5, 5), text="Authorize $145,800 to Cognizant Worldwide Limited.",
    deadline=None, source_url="https://www.cityofventura.ca.gov/doc",
)


@pytest.fixture
def backend():
    be = data_api.get_backend()
    be.execute(Path(__file__).parent.parent.joinpath("db", "schema.sql").read_text(encoding="utf-8"))
    for t in ("item_rewrites", "items", "documents", "meetings", "body_status", "bodies"):
        be.execute(f"DELETE FROM {t}")
    # FK chain: body -> meeting -> document -> item.
    be.execute("INSERT INTO bodies (body_id, name_en, category) VALUES ('city_council','City Council','legislative')")
    be.execute("INSERT INTO meetings (meeting_id, body_id, meeting_date, meeting_type) "
               "VALUES ('m1','city_council','2026-08-25'::date,'regular')")
    be.execute("INSERT INTO documents (document_id, meeting_id, url, role, status) "
               "VALUES ('doc1','m1','https://www.cityofventura.ca.gov/doc','agenda','done')")
    be.execute("INSERT INTO items (item_id, document_id, item_number, page_start, page_end) "
               "VALUES ('item1','doc1','6',5,5)")
    yield be
    for t in ("item_rewrites", "items", "documents", "meetings", "body_status", "bodies"):
        be.execute(f"DELETE FROM {t}")


def test_verified_both_round_trips(backend):
    r = ItemRewriteResult(
        source=_SRC, en_text="Plain English summary.", en_verified=True,
        es_text="Resumen en espanol.", es_verified=True, en_attempts=1, es_attempts=1,
    )
    persist_item_rewrite(backend, "item1", "run1", "amazon.nova-lite-v1:0", r)
    row = backend.query("SELECT * FROM item_rewrites WHERE item_id='item1'").rows[0]
    assert row["en_text"] == "Plain English summary."
    assert row["es_text"] == "Resumen en espanol."
    assert row["en_verified"] is True and row["es_verified"] is True
    assert row["model_id"] == "amazon.nova-lite-v1:0"


def test_es_fallback_stores_null_es_and_note(backend):
    r = ItemRewriteResult(
        source=_SRC, en_text="Verified English.", en_verified=True,
        es_text=None, es_verified=False, en_attempts=1, es_attempts=2,
        es_absent_note="A verified Spanish version was not produced for this item.",
    )
    persist_item_rewrite(backend, "item1", "run1", "amazon.nova-lite-v1:0", r)
    row = backend.query("SELECT * FROM item_rewrites WHERE item_id='item1'").rows[0]
    assert row["es_text"] is None
    assert row["es_verified"] is False
    assert "not produced" in row["es_absent_note"]
    assert row["en_text"] == "Verified English."  # reader still gets English


def test_en_fallback_stores_original_text(backend):
    r = ItemRewriteResult(
        source=_SRC, en_text=_SRC.text, en_verified=False,
        es_text=None, es_verified=False, en_attempts=2, es_attempts=0,
        note_en="showing original", es_absent_note="no verified spanish",
    )
    persist_item_rewrite(backend, "item1", "run1", "amazon.nova-lite-v1:0", r)
    row = backend.query("SELECT * FROM item_rewrites WHERE item_id='item1'").rows[0]
    assert row["en_text"] == _SRC.text  # original staff text, not a rewrite
    assert row["en_verified"] is False


def test_upsert_is_idempotent(backend):
    r = ItemRewriteResult(source=_SRC, en_text="v1", en_verified=True,
                          es_text="es1", es_verified=True, en_attempts=1, es_attempts=1)
    persist_item_rewrite(backend, "item1", "run1", "amazon.nova-lite-v1:0", r)
    r2 = ItemRewriteResult(source=_SRC, en_text="v2", en_verified=True,
                           es_text="es2", es_verified=True, en_attempts=1, es_attempts=1)
    persist_item_rewrite(backend, "item1", "run2", "amazon.nova-lite-v1:0", r2)
    rows = backend.query("SELECT * FROM item_rewrites WHERE item_id='item1'").rows
    assert len(rows) == 1  # one row, overwritten
    assert rows[0]["en_text"] == "v2" and rows[0]["run_id"] == "run2"
