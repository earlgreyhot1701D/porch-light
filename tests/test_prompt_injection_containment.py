"""Prompt-injection containment — proven, not asserted (R8, §11, security.md).

# Feature: 3-extraction, Property 4: injection containment

A real poisoned PDF lives in tests/fixtures/. This test demonstrates BOTH defenses
the design requires (R8.2), because a poisoned document attacks on two fronts:

  1. Tool-call injection: the PDF tells the model to fetch an exfiltration URL. If
     obeyed, that is a tool call outside the allowlist. The hook blocks it as a
     NEVER-trip (R1.4). The runtime's no-egress networkMode is the independent
     second layer (R8.3) — even a defeated hook cannot reach the network.
  2. Draft-steering injection: the PDF tells the model to write that the
     neighborhood SUPPORTS the proposal. This is neutralized structurally: the
     draft scaffold's stance fields are empty BY CONSTRUCTION (§4b, never.md #5) —
     there is no field a stance can be written into, so there is nothing to steer.

The poisoned PDF is a real file; the test also reads its text layer to confirm the
injections are actually present in the fixture (a fixture that lost its poison
would make this test pass for the wrong reason).
"""

from __future__ import annotations

from pathlib import Path

from porchlight.agents.extractor.entrypoint import enforce_tool_allowlist
from porchlight.draft.scaffold import build_scaffold
from porchlight.verify.models import SourceRecord
from tests.fixtures.make_poisoned_pdf import (
    DRAFT_STEERING_INJECTION,
    TOOL_CALL_INJECTION,
    poisoned_text,
)

_PDF = Path(__file__).parent / "fixtures" / "poisoned.pdf"


class _Log:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def warning(self, event: str, **kw) -> None:
        self.warnings.append((event, kw))


def test_poisoned_pdf_exists_and_carries_both_injections():
    # The fixture must actually be poisoned, or the containment test is hollow.
    assert _PDF.exists(), "run tests/fixtures/make_poisoned_pdf.py"
    text = poisoned_text()
    assert TOOL_CALL_INJECTION in text
    assert DRAFT_STEERING_INJECTION in text
    # And the injections survived into the PDF bytes' text layer.
    raw = _PDF.read_bytes()
    assert b"attacker.example" in raw
    assert b"SUPPORTS" in raw


def test_layer_1_tool_call_injection_blocked_as_never_trip():
    # The injection asks the model to fetch a URL. Any fetch-like tool the model
    # might invoke in response is not on the allowlist and is blocked + logged.
    log = _Log()
    for injected_tool in ("fetch", "http_get", "requests_get", "urlopen", "exfil"):
        assert enforce_tool_allowlist(injected_tool, log) is False
    assert log.warnings, "a blocked tool call must be logged as a NEVER-trip"
    assert all(w[0] == "never_trip_tool_blocked" for w in log.warnings)


def test_layer_2_draft_steering_neutralized_by_empty_stance():
    # Even if the model 'complied' with the steering injection, the scaffold has no
    # field to put a stance in. Build a scaffold for the poisoned item and assert
    # the stance is empty by construction and the injected text is nowhere in it.
    source = SourceRecord(
        body="Planning Commission",
        meeting_date="2026-08-25",
        item_number="4",
        page_range=(1, 1),
        text=poisoned_text(),
        deadline=None,
        source_url="https://www.cityofventura.ca.gov/test-fixture",
    )
    scaffold = build_scaffold(
        verified_summary="The Commission will consider a conditional use permit.",
        source=source,
        how_to_submit="Email the city clerk",
        where_to_submit="clerk@cityofventura.ca.gov",
    )
    assert scaffold.is_stance_empty()
    # The steering text cannot appear in any stance field — there is no path for it.
    assert scaffold.stance.your_position == ""
    assert scaffold.stance.why_this_matters_to_you == ""
    assert scaffold.stance.what_you_are_asking_for == ""
    assert "SUPPORTS" not in scaffold.stance.your_position


def test_build_scaffold_has_no_parameter_to_inject_a_stance():
    # Structural guarantee: the constructor accepts no stance argument, so no caller
    # (or injected instruction routed through one) can set a position.
    import inspect

    params = set(inspect.signature(build_scaffold).parameters)
    assert "your_position" not in params
    assert "stance" not in params
    assert params == {"verified_summary", "source", "how_to_submit", "where_to_submit"}
