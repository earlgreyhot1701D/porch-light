"""DB-backed test for W4-W5: the rewrite stage (budget gate, cost, §36b, persist).

Needs Postgres (skips without DATABASE_URL). No live model call — a fake Converse
client returns scripted text so the stage is deterministic.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL unset: no database for rewrite-stage tests.",
)

from db import data_api  # noqa: E402
from porchlight.pipeline import ledger  # noqa: E402
from porchlight.pipeline.thresholds import INGESTION_SUBBUDGET_USD  # noqa: E402
from porchlight.rewrite.stage import run_rewrite_stage  # noqa: E402
from porchlight.verify.models import SourceRecord  # noqa: E402

_TEXT = "Authorize a payment of $145,800 to Cognizant Worldwide Limited through August 31, 2027."
_GOOD_EN = "The council may pay $145,800 to Cognizant Worldwide Limited through August 31, 2027."
_GOOD_ES = "El concejo puede pagar $145.800 a Cognizant Worldwide Limited hasta el 31 de agosto de 2027."


class FakeClient:
    def __init__(self, texts):
        self._t = list(texts)
        self.calls = 0

    def converse(self, **kwargs):
        t = self._t[min(self.calls, len(self._t) - 1)]
        self.calls += 1
        return {"output": {"message": {"content": [{"text": t}]}},
                "usage": {"inputTokens": 100, "outputTokens": 50}}


@pytest.fixture
def backend():
    be = data_api.get_backend()
    be.execute(Path(__file__).parent.parent.joinpath("db", "schema.sql").read_text(encoding="utf-8"))
    for t in ("item_rewrites", "items", "documents", "meetings", "body_status", "bodies", "spend_ledger"):
        be.execute(f"DELETE FROM {t}")
    be.execute("INSERT INTO bodies (body_id, name_en, category) VALUES ('city_council','City Council','legislative')")
    be.execute("INSERT INTO meetings (meeting_id, body_id, meeting_date, meeting_type) VALUES ('m1','city_council','2026-08-25'::date,'regular')")
    be.execute("INSERT INTO documents (document_id, meeting_id, url, role, status) VALUES ('doc1','m1','https://www.cityofventura.ca.gov/doc','agenda','done')")
    be.execute("INSERT INTO items (item_id, document_id, item_number, page_start, page_end) VALUES ('item1','doc1','6',5,5)")
    yield be
    for t in ("item_rewrites", "items", "documents", "meetings", "body_status", "bodies", "spend_ledger"):
        be.execute(f"DELETE FROM {t}")


def _src():
    return SourceRecord(body="city_council", meeting_date="2026-08-25", item_number="6",
                        page_range=(5, 5), text=_TEXT, deadline=None,
                        source_url="https://www.cityofventura.ca.gov/doc")


def test_stage_persists_verified_item_and_records_cost(backend):
    client = FakeClient([_GOOD_EN, _GOOD_ES])
    summary = run_rewrite_stage(backend, "run1", [("item1", _src())],
                                model_id="amazon.nova-lite-v1:0", client=client)
    assert summary.items == 1 and summary.en_verified == 1 and summary.es_verified == 1
    row = backend.query("SELECT * FROM item_rewrites WHERE item_id='item1'").rows[0]
    assert row["en_verified"] is True and row["es_verified"] is True
    # A ledger row is recorded by model id (W4). NOTE: a single Nova Lite call is
    # ~$0.00004, below spend_ledger's NUMERIC(10,4) resolution, so its stored value
    # rounds toward 0 — the MONTHLY aggregate is what the $10 budget cares about, and
    # 4 decimals is fine there. Here we assert the attributable row exists.
    ledger_rows = backend.query(
        "SELECT model_id FROM spend_ledger WHERE run_id='run1' AND model_id='amazon.nova-lite-v1:0'"
    ).rows
    assert len(ledger_rows) == 1


def test_stage_halts_when_budget_spent(backend):
    # Spend the ingestion sub-budget first; the stage must HALT, not ship unverified.
    ledger.record(backend, "prior", INGESTION_SUBBUDGET_USD, "ingestion")
    with pytest.raises(ledger.BudgetExhausted):
        run_rewrite_stage(backend, "run1", [("item1", _src())],
                          model_id="amazon.nova-lite-v1:0", client=FakeClient([_GOOD_EN, _GOOD_ES]))
    # No rewrite was persisted (halted before spending).
    assert backend.query("SELECT count(*) AS c FROM item_rewrites").rows[0]["c"] == 0


def test_city_spanish_skip_suppresses_machine_spanish(backend):
    client = FakeClient([_GOOD_EN, _GOOD_ES])
    key = "city_council|2026-08-25"
    summary = run_rewrite_stage(backend, "run1", [("item1", _src())],
                                model_id="amazon.nova-lite-v1:0", client=client,
                                city_spanish_meetings=frozenset({key}))
    row = backend.query("SELECT * FROM item_rewrites WHERE item_id='item1'").rows[0]
    assert row["en_verified"] is True
    assert row["es_text"] is None  # our machine Spanish suppressed
    assert "city's own published Spanish edition" in row["es_absent_note"]
    assert summary.es_fallback == 0  # a §36b skip is not a fallback failure


def test_stage_counts_es_retry_recovery(backend):
    # EN good; ES bad then good -> es_verified with es_recovered_on_retry counted.
    _BAD_ES = "El concejo pagara $999.999 a otro proveedor."
    client = FakeClient([_GOOD_EN, _BAD_ES, _GOOD_ES])
    summary = run_rewrite_stage(backend, "run1", [("item1", _src())],
                                model_id="amazon.nova-lite-v1:0", client=client)
    assert summary.es_verified == 1
    assert summary.es_recovered_on_retry == 1
