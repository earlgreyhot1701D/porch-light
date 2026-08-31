"""Contract test for the deployed extractor's structured return envelope.

testing.md #3: build the contract test from a CAPTURED REAL response, not a hand-
written shape. The fixture `extractor_response_3687_strands-1.53.0_2026-08-31.json`
is the verbatim `porchlight_result` envelope the DEPLOYED runtime returned for
meeting 3687 (strands-agents 1.53.0, captured 2026-08-31). This test pins the shape
the join relies on when it parses `invoke_agent_runtime` output; if a redeploy
changes the envelope, this fails.

Offline: reads the captured file, asserts the contract. No AWS calls.
"""
from __future__ import annotations

import json
import os

import pytest

FIXTURE = os.path.join(
    os.path.dirname(__file__),
    "extractor_response_3687_strands-1.53.0_2026-08-31.json",
)


@pytest.fixture
def envelope() -> dict:
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_top_level_shape(envelope: dict) -> None:
    assert "porchlight_result" in envelope, "join parses response for the porchlight_result key"
    r = envelope["porchlight_result"]
    for key in ("document_id", "items", "rejected", "omissions", "status", "turns_used", "tokens_used", "model_id"):
        assert key in r, f"envelope missing '{key}' — the join reads this field"
    assert isinstance(r["items"], list) and isinstance(r["rejected"], list)
    assert isinstance(r["omissions"], list), "omissions surfaces silently-dropped items (§46)"
    assert isinstance(r["turns_used"], int) and isinstance(r["tokens_used"], int)


def test_items_shape(envelope: dict) -> None:
    """Every item carries the three receipt-critical fields the join persists."""
    items = envelope["porchlight_result"]["items"]
    assert items, "the captured 3687 response had four items; an empty list is a regression"
    for it in items:
        assert set(it.keys()) == {"item_number", "page_range", "text"}, (
            f"item shape drifted: {sorted(it.keys())}"
        )
        assert isinstance(it["item_number"], str)
        pr = it["page_range"]
        assert isinstance(pr, list) and len(pr) == 2 and all(isinstance(n, int) for n in pr)
        assert pr[0] <= pr[1]
        assert isinstance(it["text"], str) and it["text"].strip()


def test_status_shape(envelope: dict) -> None:
    status = envelope["porchlight_result"]["status"]
    for key in ("partially_read", "stop_reason", "source_url", "reason"):
        assert key in status, f"status missing '{key}'"
    assert isinstance(status["partially_read"], bool)


def test_captured_values_are_the_real_3687_extraction(envelope: dict) -> None:
    """Pin the actual captured content so a silent re-capture with different data is visible.

    Values reflect the condition-5 re-run after the §45/§46 fixes: item numbers carry
    a trailing '.' (normalized downstream), the model recorded items 1/3/4 and the §46
    backstop recorded item 2 as an omission (a real run-to-run variance the join
    documents). Item numbers are compared with the trailing dot stripped so this test
    pins CONTENT, not the cosmetic dot.
    """
    r = envelope["porchlight_result"]
    assert r["model_id"] == "amazon.nova-lite-v1:0"
    assert r["status"]["partially_read"] is False

    nums = sorted(it["item_number"].rstrip(".") for it in r["items"])
    omitted = sorted(o["item_number"].rstrip(".") for o in r["omissions"])
    # Every numbered item 1-4 is accounted for: recorded OR omitted, never lost (§46).
    assert sorted(nums + omitted) == ["1", "2", "3", "4"], (
        f"3687 items+omissions no longer cover 1-4: items={nums} omissions={omitted}"
    )
    # Item 1 is the minutes item (its text is the draft-minutes approval).
    item1 = next(it for it in r["items"] if it["item_number"].rstrip(".") == "1")
    assert "draft minutes" in item1["text"].lower()
