"""DB-backed ingestion tests (Spec 2): idempotency, ledger, and the pass gates.

# Feature: 2-ingestion, Property 1: idempotency

Need a real Postgres. Skip cleanly when DATABASE_URL is unset; fail on any error
from a DB that exists (Spec 0 skip-vs-fail discipline). Fetch is faked so these
run offline and deterministically — we are testing the pipeline's idempotency and
ledger logic, not the network.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "db"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL unset: no database for ingestion tests.",
)

from porchlight.adapters.ventura import fetch as vfetch  # noqa: E402
from porchlight.adapters.ventura.fetch import FetchResult  # noqa: E402
from porchlight.pipeline import changedetect, ledger  # noqa: E402


@pytest.fixture()
def backend():
    import data_api

    be = data_api.get_backend()
    be.execute(Path(__file__).parent.parent.joinpath("db", "schema.sql").read_text(encoding="utf-8"))
    # Clean slate for the tables these tests touch.
    for t in ("spend_ledger", "documents", "meetings", "body_status", "bodies"):
        be.execute(f"DELETE FROM {t}")
    # A body + meeting to attach documents to (FKs).
    be.execute("INSERT INTO bodies (body_id, name_en, category) VALUES ('city_council','City Council','legislative')")
    be.execute(
        "INSERT INTO meetings (meeting_id, body_id, meeting_date, meeting_type) "
        "VALUES ('m1','city_council','2026-02-10','regular')"
    )
    yield be
    for t in ("spend_ledger", "documents", "meetings", "body_status", "bodies"):
        be.execute(f"DELETE FROM {t}")


def _fake_fetch(monkeypatch, body: bytes | None, status: int = 200,
                last_modified: str | None = "Mon, 01 Jan 2026 00:00:00 GMT"):
    def fake(url, if_modified_since=None, if_none_match=None):
        return FetchResult(url=url, status=status, body=body,
                           last_modified=last_modified, etag=None)
    monkeypatch.setattr(vfetch, "fetch", fake)


URL = "https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_02102026-m1"


def test_first_record_writes_one_row(backend, monkeypatch):
    _fake_fetch(monkeypatch, b"agenda bytes v1")
    out = changedetect.record_document(backend, URL, "m1", "agenda", "run1")
    assert out.changed is True
    r = backend.query("SELECT count(*) AS c FROM documents")
    assert int(r.rows[0]["c"]) == 1


def test_identical_bytes_are_idempotent(backend, monkeypatch):
    """Property (pass gate): recording the same bytes twice yields one row, not two."""
    _fake_fetch(monkeypatch, b"agenda bytes v1")
    changedetect.record_document(backend, URL, "m1", "agenda", "run1")
    out2 = changedetect.record_document(backend, URL, "m1", "agenda", "run2")
    assert out2.changed is False
    assert out2.unchanged is True
    r = backend.query("SELECT count(*) AS c FROM documents")
    assert int(r.rows[0]["c"]) == 1  # still one row


def test_second_run_unchanged_writes_nothing(backend, monkeypatch):
    """Pass gate 1: a 304 (unchanged) writes no new row and reports unchanged."""
    _fake_fetch(monkeypatch, b"agenda bytes v1")
    changedetect.record_document(backend, URL, "m1", "agenda", "run1")
    before = int(backend.query("SELECT count(*) AS c FROM documents").rows[0]["c"])
    _fake_fetch(monkeypatch, None, status=304)  # not modified
    out = changedetect.record_document(backend, URL, "m1", "agenda", "run2")
    after = int(backend.query("SELECT count(*) AS c FROM documents").rows[0]["c"])
    assert out.unchanged is True
    assert before == after == 1


def test_changed_bytes_record_new_document(backend, monkeypatch):
    _fake_fetch(monkeypatch, b"agenda bytes v1")
    changedetect.record_document(backend, URL, "m1", "agenda", "run1")
    _fake_fetch(monkeypatch, b"agenda bytes v2 AMENDED")
    out = changedetect.record_document(backend, URL, "m1", "agenda", "run2")
    assert out.changed is True
    # Two distinct content hashes → two rows (the amendment is a new document).
    r = backend.query("SELECT count(*) AS c FROM documents")
    assert int(r.rows[0]["c"]) == 2


def test_crash_restart_double_writes_nothing(backend, monkeypatch):
    """Pass gate 2: simulate a crash after recording, then a restart over the same
    input. The content-hash upsert means the restart adds no duplicate row."""
    _fake_fetch(monkeypatch, b"agenda bytes v1")
    changedetect.record_document(backend, URL, "m1", "agenda", "run1")  # "before crash"
    # "restart": same bytes seen again
    _fake_fetch(monkeypatch, b"agenda bytes v1")
    changedetect.record_document(backend, URL, "m1", "agenda", "run1_restart")
    r = backend.query("SELECT count(*) AS c FROM documents")
    assert int(r.rows[0]["c"]) == 1


# --- ledger ---

def test_ledger_check_passes_when_under_budget(backend):
    ledger.check_before_run(backend, "ingestion")  # no spend yet → ok


def test_ledger_halts_when_subbudget_spent(backend):
    from porchlight.pipeline.thresholds import INGESTION_SUBBUDGET_USD
    ledger.record(backend, "run1", INGESTION_SUBBUDGET_USD, "ingestion")
    with pytest.raises(ledger.BudgetExhausted):
        ledger.check_before_run(backend, "ingestion")


def test_ledger_subbudgets_are_separate(backend):
    """Search exhaustion must not halt ingestion (§18b)."""
    from porchlight.pipeline.thresholds import SEARCH_SUBBUDGET_USD
    ledger.record(backend, "run1", SEARCH_SUBBUDGET_USD, "search")
    # Search is spent, but ingestion is untouched → ingestion still runs.
    ledger.check_before_run(backend, "ingestion")
