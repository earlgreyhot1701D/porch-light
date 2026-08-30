"""The six verifier checks — pure functions, no model, no I/O (R3, §4).

Each check takes a `Rewrite`, its `SourceRecord`, and returns a `CheckResult`.
The checks are the product's spine: a check that PASSES a rewrite it should
reject is the worst invisible failure in the system (a fabricated summary shipped
with a receipt). So each has its own property tests (task 3.2), and each is small
enough to read in one sitting.

Design mapping (design.md "The six-check verifier"):
  1. schema           — structured output present.
  2. entity_preservation — every normalized output entity is in the source.
  3. no_new_entities  — every normalized output entity has a source origin.
  4. containment      — id/page-range/deadline/body equal the extraction record.
  5. reading_level    — simpler than source by the per-language metric.
  6. both_languages   — checks 2/3 on the ES output against the (English) source.

Check 5's threshold is NOT hardcoded: it is passed in, derived from the golden set
at calibration (task 8). Guessing it here is the "TBD-at-build" calibration
replaces.
"""

from __future__ import annotations

from porchlight.verify.entities import extract
from porchlight.verify.models import CheckResult, Language, Rewrite, SourceRecord
from porchlight.verify.normalize import normalize_all
from porchlight.verify.reading import Language as RLang
from porchlight.verify.reading import score


def check_schema(rewrite: Rewrite) -> CheckResult:
    """Check 1: the output has the required structure before anything else runs."""
    if not isinstance(rewrite.summary, str) or not rewrite.summary.strip():
        return CheckResult("schema", False, "summary is empty or not a string")
    if rewrite.language not in (Language.EN, Language.ES):
        return CheckResult("schema", False, f"unknown language {rewrite.language!r}")
    return CheckResult("schema", True)


def check_entity_preservation(rewrite: Rewrite, source: SourceRecord) -> CheckResult:
    """Check 2: every normalized entity in the output is present in the source.

    A rewrite that INVENTS a date, amount, or name (not in the source page range)
    fails. Comparison is on normalized entities so an EN->ES translated date still
    counts as present.
    """
    src = normalize_all(extract(source.text))
    out = normalize_all(extract(rewrite.summary))
    invented = out - src
    if invented:
        return CheckResult(
            "entity_preservation",
            False,
            f"output entities not found in source: {sorted(e.key for e in invented)}",
        )
    return CheckResult("entity_preservation", True)


def check_no_new_entities(rewrite: Rewrite, source: SourceRecord) -> CheckResult:
    """Check 3: no entity appears in the output that has no origin in the source.

    Distinct from check 2 in intent: check 2 guards against a WRONG value, check 3
    against an ADDED one. Reference-resolution ("the property on Main Street" where
    the source used an APN) is what calibration (task 8) narrows — a resident-useful
    reference is not a forbidden new entity. The current rule is strict (any
    normalized output entity absent from source fails) and calibration records any
    narrowing.
    """
    src = normalize_all(extract(source.text))
    out = normalize_all(extract(rewrite.summary))
    added = out - src
    if added:
        return CheckResult(
            "no_new_entities",
            False,
            f"new entities absent from source: {sorted(e.key for e in added)}",
        )
    return CheckResult("no_new_entities", True)


def check_containment(rewrite: Rewrite, source: SourceRecord) -> CheckResult:
    """Check 4: receipt fields come from the record, never from model output.

    If the model returned an item number / page range / deadline / body, it must
    match the extraction record exactly. Any drift fails — the shown receipt always
    comes from the record, and this check catches a model trying to author one.
    Empty claimed fields are fine (the model was not asked to produce them); a
    non-empty claimed field that disagrees with the record is a failure.
    """
    mismatches: list[str] = []
    if rewrite.claimed_item_number and rewrite.claimed_item_number != source.item_number:
        mismatches.append(
            f"item_number {rewrite.claimed_item_number!r} != record {source.item_number!r}"
        )
    if rewrite.claimed_page_range is not None and rewrite.claimed_page_range != source.page_range:
        mismatches.append(
            f"page_range {rewrite.claimed_page_range} != record {source.page_range}"
        )
    if rewrite.claimed_deadline and rewrite.claimed_deadline != source.deadline:
        mismatches.append(
            f"deadline {rewrite.claimed_deadline!r} != record {source.deadline!r}"
        )
    if rewrite.claimed_body and rewrite.claimed_body != source.body:
        mismatches.append(f"body {rewrite.claimed_body!r} != record {source.body!r}")
    if mismatches:
        return CheckResult("containment", False, "; ".join(mismatches))
    return CheckResult("containment", True)


# Check-5 "already-plain source" tuning. PROVISIONAL, derived from the task-9
# Nova-Lite ES data. The "strictly simpler" rule is right for DENSE source and
# wrong for source that is already plain (a faithful rewrite of already-plain text
# cannot be much simpler, yet it is fine). So the rule is conditional on how plain
# the source already is.
#
# Derivation (observed Nova-Lite ES, post-fix): source Fernandez Huerta scores split
# cleanly into one dense source (golden-005, 61.7, whose rewrite genuinely simplified
# to 84.3) and three already-plain sources (golden-001 74.9, 006 76.5, 003 77.7,
# whose faithful rewrites landed at 73.8 / 75.8 / 70.6). So:
#   - ALREADY_PLAIN_SOURCE = 70.0: above the dense source (61.7), below the lowest
#     already-plain source (74.9); separates the two regimes.
#   - PLAIN_SOURCE_TOLERANCE = 8.0: the worst acceptable good-rewrite gap on plain
#     source was golden-003 at -7.1 (70.6 vs 77.7); 8.0 = 7.1 + a small margin. On
#     already-plain source a rewrite passes if it clears the floor and is no more
#     than 8.0 points HARDER than the source.
# Both provisional (small n, one meeting, one model); revisit at task 0b.
ALREADY_PLAIN_SOURCE = 70.0
PLAIN_SOURCE_TOLERANCE = 8.0


def check_reading_level(rewrite: Rewrite, source: SourceRecord, floor: float) -> CheckResult:
    """Check 5: readable per-language, and simplified WHEN the source needed it (R3b).

    Always requires the rewrite to clear the per-language `floor` (derived at
    calibration). The "did it simplify" condition is CONDITIONAL on source density:

      - DENSE source (source score < ALREADY_PLAIN_SOURCE): the rewrite must be
        strictly simpler than the source — if dense text did not get simpler, the
        rewrite did not do its job.
      - ALREADY-PLAIN source (source score >= ALREADY_PLAIN_SOURCE): a faithful
        rewrite of already-plain text cannot be much simpler, so it need only clear
        the floor and be no more than PLAIN_SOURCE_TOLERANCE points HARDER than the
        source. This is what keeps a good Spanish rewrite of a short consent item
        from being rejected (Spanish shipping, not "measuring oddly").
    """
    rlang = RLang.ES if rewrite.language is Language.ES else RLang.EN
    out_score = score(rewrite.summary, rlang).score
    src_score = score(source.text, rlang).score

    if out_score < floor:
        return CheckResult(
            "reading_level",
            False,
            f"reading score {out_score:.1f} below floor {floor:.1f} ({rlang.value})",
        )

    if src_score < ALREADY_PLAIN_SOURCE:
        # Dense source: must be strictly simpler than the source.
        if out_score <= src_score:
            return CheckResult(
                "reading_level",
                False,
                f"dense source ({src_score:.1f}); rewrite ({out_score:.1f}) not simpler",
            )
        return CheckResult("reading_level", True)

    # Already-plain source: clear the floor and do not get MORE than tolerance harder.
    if out_score < src_score - PLAIN_SOURCE_TOLERANCE:
        return CheckResult(
            "reading_level",
            False,
            f"already-plain source ({src_score:.1f}); rewrite ({out_score:.1f}) "
            f"harder than source by more than {PLAIN_SOURCE_TOLERANCE:.1f}",
        )
    return CheckResult("reading_level", True)


def check_both_languages(spanish: Rewrite, source: SourceRecord) -> CheckResult:
    """Check 6: the Spanish rewrite passes entity preservation + no-new against source.

    Runs checks 2 and 3 on the ES output against the (English) source. Because
    comparison is on normalized entities, translated dates/amounts match; a street
    or body name that changed in translation does NOT match and correctly fails.
    """
    if spanish.language is not Language.ES:
        return CheckResult("both_languages", False, "expected a Spanish rewrite")
    preservation = check_entity_preservation(spanish, source)
    if not preservation.passed:
        return CheckResult("both_languages", False, f"ES {preservation.reason}")
    no_new = check_no_new_entities(spanish, source)
    if not no_new.passed:
        return CheckResult("both_languages", False, f"ES {no_new.reason}")
    return CheckResult("both_languages", True)
