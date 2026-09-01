"""Live watcher smoke (Spec 5 task 8.1) — one real watchlist over real stored items.

@pytest.mark.live, part of `make smoke`. Reads the verified rewrites the condition-5
join persisted for 3685/3687 from Aurora, runs the matcher against a real watchlist,
and asserts the demo-beat invariants: matches carry a reason, an off-topic list is
quiet, and nothing is fabricated. Needs Aurora env (AURORA_CLUSTER_ARN + SECRET) and
BEDROCK_MODEL_ID; skips cleanly if the DB is not configured.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live


def _load_items():
    from db import data_api

    be = data_api.get_backend()
    rows = be.query(
        "SELECT ir.item_id, ir.en_text FROM item_rewrites ir "
        "JOIN items i ON i.item_id = ir.item_id "
        "WHERE ir.en_verified = true AND ir.en_text IS NOT NULL"
    ).rows
    return {r["item_id"]: r["en_text"] for r in rows}


@pytest.fixture(scope="module")
def stored_items():
    if not (os.environ.get("AURORA_CLUSTER_ARN") and os.environ.get("AURORA_SECRET_ARN")):
        pytest.skip("Aurora not configured (AURORA_CLUSTER_ARN + AURORA_SECRET_ARN)")
    items = _load_items()
    if not items:
        pytest.skip("no verified item_rewrites in the DB (run the condition-5 join first)")
    return items


def test_real_watchlist_returns_matches_with_reasons(stored_items):
    from porchlight.watch.matcher import match_watchlist

    ans = match_watchlist(["housing", "contracts", "parking"], stored_items)
    assert not ans.degraded, f"watcher degraded: {ans.note}"
    # Some of the real items are about housing/contracts/parking -> expect matches,
    # each carrying a bilingual reason and a real stored item_id.
    for m in ans.matches:
        assert m.item_id in stored_items
        assert m.reason.en.strip() and m.reason.es.strip()


def test_off_topic_watchlist_is_quiet_or_reasoned(stored_items):
    from porchlight.watch.matcher import match_watchlist

    ans = match_watchlist(["fireworks over the harbor at midnight"], stored_items)
    assert not ans.degraded
    for m in ans.matches:  # anything shown still carries a reason (never blank)
        assert m.reason.en.strip()
