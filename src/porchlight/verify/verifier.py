"""Verifier orchestration — run the six checks; one retry; else original text (R3.3).

`verify()` is pure: it runs the checks that apply to a single rewrite and returns
a verdict. The retry/fallback POLICY (`verify_with_retry`) is code deciding after
checking — a retry, never a loop (§model-authority): fail once, retry the rewrite
ONCE with the failure reason attached; fail twice, show the original staff text
with a note and count the rejection. The model never grades its own output; this
module is the grader, and it is deterministic code.

The rewrite function is injected (the model does not exist until task 9), so this
module has no model dependency and is fully testable against fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from porchlight.verify import checks
from porchlight.verify.models import (
    CheckResult,
    Language,
    Rewrite,
    SourceRecord,
    VerifyResult,
)


def verify(
    rewrite: Rewrite,
    source: SourceRecord,
    reading_floor: float,
    spanish: Rewrite | None = None,
) -> VerifyResult:
    """Run the applicable checks on one rewrite against its source record.

    Checks 1-5 run on the given rewrite. Check 6 runs only when a Spanish rewrite
    is supplied (the EN pass supplies `spanish`, or an ES rewrite is verified
    directly). `reading_floor` is derived from the golden set at calibration.
    """
    results: list[CheckResult] = [
        checks.check_schema(rewrite),
        checks.check_entity_preservation(rewrite, source),
        checks.check_no_new_entities(rewrite, source),
        checks.check_containment(rewrite, source),
        checks.check_reading_level(rewrite, source, reading_floor),
    ]
    if spanish is not None:
        results.append(checks.check_both_languages(spanish, source))
    elif rewrite.language is Language.ES:
        results.append(checks.check_both_languages(rewrite, source))

    ok = all(r.passed for r in results)
    return VerifyResult(ok=ok, results=tuple(results))


@dataclass(frozen=True)
class RewriteOutcome:
    """The end state of one item after the verify/retry/fallback policy.

    `shown_original` True means both attempts failed and the ORIGINAL staff text is
    shown with a note (R3.3) — a rejection, counted for §27 model selection.
    `attempts` is 1 or 2. `final` is the accepted rewrite, or None when the original
    is shown.
    """

    shown_original: bool
    attempts: int
    final: Rewrite | None
    last_result: VerifyResult
    note: str = ""


def verify_with_retry(
    source: SourceRecord,
    reading_floor: float,
    rewrite_fn: Callable[[SourceRecord, str], Rewrite],
    language: Language,
    spanish_fn: Callable[[SourceRecord, Rewrite], Rewrite] | None = None,
) -> RewriteOutcome:
    """Verify a rewrite; on first failure retry once with the reason; else show original.

    Args:
        source: the extraction record (ground truth).
        reading_floor: derived per-language floor for check 5.
        rewrite_fn: (source, failure_reason) -> Rewrite. First call gets "".
        language: which language this pass produces.
        spanish_fn: optional (source, verified_en) -> ES rewrite, for the chain's
            second stage; when given, check 6 runs against the produced ES.

    Returns:
        A RewriteOutcome. Never raises the model's errors into the caller: this is
        the deterministic grader, so it fails safe to showing the original text.
    """
    reason = ""
    last: VerifyResult | None = None
    final_rewrite: Rewrite | None = None

    for attempt in (1, 2):
        candidate = rewrite_fn(source, reason)
        spanish = spanish_fn(source, candidate) if spanish_fn is not None else None
        last = verify(candidate, source, reading_floor, spanish=spanish)
        if last.ok:
            final_rewrite = candidate
            return RewriteOutcome(
                shown_original=False,
                attempts=attempt,
                final=final_rewrite,
                last_result=last,
            )
        reason = last.first_failure

    # Failed twice: show the original staff text with a note (R3.3, never.md #7).
    assert last is not None
    return RewriteOutcome(
        shown_original=True,
        attempts=2,
        final=None,
        last_result=last,
        note="Showing original staff text: automated summary could not be verified.",
    )
