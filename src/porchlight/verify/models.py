"""Verifier data models — the shapes the six checks operate on.

Frozen dataclasses, no behavior, no I/O. These separate the two things check 4
(containment) exists to keep separate: what the MODEL produced (`Rewrite`) and
what the deterministic extraction RECORDED (`SourceRecord`). The receipt fields —
item number, page range, deadline, body — live only on the record and are never
read from model output (never.md #1, #6; §4 check 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Language(str, Enum):
    EN = "en"
    ES = "es"


@dataclass(frozen=True)
class SourceRecord:
    """The deterministic extraction record for one item — the ground truth.

    `text` is the verbatim source page-range text the rewrite must be faithful to.
    The receipt fields are attached here by the extractor (copied from source),
    never by the model, and check 4 asserts the rewrite carries them unchanged.
    """

    body: str
    """Body name, copied from source (compared raw — never translated)."""

    meeting_date: str
    """ISO 8601 date string, from the extraction record."""

    item_number: str
    """Copied from the source document, never generated."""

    page_range: tuple[int, int]
    """(first_page, last_page), copied from the source document."""

    text: str
    """Verbatim staff text for this item's page range — what the rewrite is checked against."""

    deadline: str | None = None
    """Comment deadline copied from source, or None if the source states none."""

    source_url: str = ""
    """The receipt's source link."""


@dataclass(frozen=True)
class Rewrite:
    """A model-produced rewrite in ONE language, plus the receipt it claims.

    The receipt fields here are what the model RETURNED; check 4 compares them
    against the SourceRecord and rejects any drift. They exist on the rewrite only
    so the check has something to compare — the shown receipt always comes from the
    record, never from these.
    """

    language: Language
    summary: str
    """The plain-language rewrite of the source text."""

    claimed_item_number: str = ""
    claimed_page_range: tuple[int, int] | None = None
    claimed_deadline: str | None = None
    claimed_body: str = ""


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check: passed, plus a reason when it did not."""

    check: str
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class VerifyResult:
    """The verifier's verdict on one rewrite: all six checks, pass/fail, reasons.

    `ok` is True only if every check passed. `first_failure` is the reason to
    attach to a retry (the single most informative failing check), or "" if none.
    """

    ok: bool
    results: tuple[CheckResult, ...]

    @property
    def first_failure(self) -> str:
        for r in self.results:
            if not r.passed:
                return f"{r.check}: {r.reason}"
        return ""

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(r.check for r in self.results if not r.passed)
