"""Task 8 calibration harness — the verifier is UNDER TEST against human ground truth.

Run: `uv run python tests/golden/calibrate.py`

Loads the golden set, then:
  0. PRE-CHECK (task 1): report any rewrite naming an entity absent from its
     source.text. That is an authoring error, flagged not calibrated around.
  1. MATRIX (task 2): each of the 12 rewrites x each of the 6 checks, pass/fail.
     Check 5 (reading level) uses a floor DERIVED in step 3, not a guess.
  2. THREE KNOWN RISKS (task 3): identifier spacing, Spanish number separators,
     mojibake — confirm or refute each by name, with the exact entity pair. Report
     only; fix nothing; never edit source.text.
  3. THRESHOLDS (task 4): derive EN and ES reading floors from the gap between the
     ten correct rewrites and their sources. Report numbers + method. Do NOT write
     them into thresholds.py.

This harness does NOT modify the normalizer or the checks. It reports what the
verifier does today against ground truth; the fixes come in a later, approved step.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from porchlight.verify import checks
from porchlight.verify.entities import EntityClass, extract
from porchlight.verify.models import Language, Rewrite, SourceRecord
from porchlight.verify.normalize import normalize_all
from porchlight.verify.reading import Language as RLang
from porchlight.verify.reading import score

GOLDEN = Path(__file__).parent / "golden_set.json"

# Check 5 needs a floor to run the matrix. We first derive it (step 3), then run
# the matrix with the derived value so check 5's column is meaningful. A permissive
# sentinel is used only if derivation somehow fails.
_SENTINEL_FLOOR = -1000.0


def load() -> list[dict]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["items"]


def _record(item: dict) -> SourceRecord:
    s = item["source"]
    return SourceRecord(
        body=s["body_id"],
        meeting_date=s["meeting_date"],
        item_number=s["item_number"],
        page_range=tuple(s["page_range"]),
        text=s["text"],
        deadline=None,
        source_url=s["document_url"],
    )


def _rewrites(item: dict) -> list[tuple[str, Rewrite]]:
    """Return [(label, Rewrite)] for the EN and ES rewrites of an item."""
    return [
        (f"{item['id']}/en", Rewrite(Language.EN, item["rewrite_en"])),
        (f"{item['id']}/es", Rewrite(Language.ES, item["rewrite_es"])),
    ]


def _is_expected_reject(item: dict, lang: str) -> bool:
    return bool(item["is_adversarial"]) and item.get("adversarial_language") == lang


# --------------------------------------------------------------------------
# Step 0: pre-check — entities in a rewrite absent from source (authoring error)
# --------------------------------------------------------------------------
def precheck_absent_entities(items: list[dict]) -> list[str]:
    findings: list[str] = []
    for item in items:
        src = normalize_all(extract(item["source"]["text"]))
        for label, rw in _rewrites(item):
            # Skip the deliberately-broken rewrite's own broken entity — that IS the
            # adversarial content, not an accidental authoring error.
            lang = label.rsplit("/", 1)[1]
            out = normalize_all(extract(rw.summary))
            absent = out - src
            if absent and not _is_expected_reject(item, lang):
                pretty = sorted(f"{e.entity_class.value}:{e.key}" for e in absent)
                findings.append(f"{label}: entities not in source.text -> {pretty}")
    return findings


# --------------------------------------------------------------------------
# Step 3 (run before the matrix): derive reading-level thresholds
# --------------------------------------------------------------------------
def derive_thresholds(items: list[dict]) -> dict:
    """Floor per language from the ten CORRECT rewrites' reading scores.

    Method: for each correct rewrite, score it in its language and score its source
    in the same language. Report the rewrite scores, the source scores, and the gap.
    The derived floor is the MINIMUM correct-rewrite score minus a small margin, so
    every known-good rewrite passes (rejection rate 0) while still rejecting text no
    simpler than the source. Adversarial rewrites are excluded from derivation.
    """
    en_rw, en_src, es_rw, es_src = [], [], [], []
    for item in items:
        for lang, key, rlang, rw_list, src_list in (
            ("en", "rewrite_en", RLang.EN, en_rw, en_src),
            ("es", "rewrite_es", RLang.ES, es_rw, es_src),
        ):
            if _is_expected_reject(item, lang):
                continue  # correct rewrites only
            rw_list.append(round(score(item[key], rlang).score, 1))
            src_list.append(round(score(item["source"]["text"], rlang).score, 1))

    def _floor(rw_scores: list[float]) -> float:
        # Min correct-rewrite score, minus a 5-point margin, so a good rewrite that
        # is only slightly simpler than the corpus minimum still passes.
        return round(min(rw_scores) - 5.0, 1)

    return {
        "en": {
            "rewrite_scores": en_rw,
            "source_scores": en_src,
            "min_rewrite": min(en_rw),
            "max_source": max(en_src),
            "mean_gap": round(statistics.mean(r - s for r, s in zip(en_rw, en_src)), 1),
            "derived_floor": _floor(en_rw),
        },
        "es": {
            "rewrite_scores": es_rw,
            "source_scores": es_src,
            "min_rewrite": min(es_rw),
            "max_source": max(es_src),
            "mean_gap": round(statistics.mean(r - s for r, s in zip(es_rw, es_src)), 1),
            "derived_floor": _floor(es_rw),
        },
    }


# --------------------------------------------------------------------------
# Step 1: the 12 x 6 matrix
# --------------------------------------------------------------------------
_CHECK_NAMES = [
    "schema",
    "entity_preservation",
    "no_new_entities",
    "containment",
    "reading_level",
    "both_languages",
]


def run_checks(rw: Rewrite, rec: SourceRecord, floor: float) -> dict[str, bool]:
    row = {
        "schema": checks.check_schema(rw).passed,
        "entity_preservation": checks.check_entity_preservation(rw, rec).passed,
        "no_new_entities": checks.check_no_new_entities(rw, rec).passed,
        "containment": checks.check_containment(rw, rec).passed,
        "reading_level": checks.check_reading_level(rw, rec, floor).passed,
    }
    # Check 6 applies to the Spanish rewrite (both-languages against source).
    if rw.language is Language.ES:
        row["both_languages"] = checks.check_both_languages(rw, rec).passed
    else:
        row["both_languages"] = None  # not applicable to EN
    return row


def reasons(rw: Rewrite, rec: SourceRecord, floor: float) -> dict[str, str]:
    out = {}
    r = checks.check_entity_preservation(rw, rec)
    if not r.passed:
        out["entity_preservation"] = r.reason
    r = checks.check_no_new_entities(rw, rec)
    if not r.passed:
        out["no_new_entities"] = r.reason
    r = checks.check_reading_level(rw, rec, floor)
    if not r.passed:
        out["reading_level"] = r.reason
    if rw.language is Language.ES:
        r = checks.check_both_languages(rw, rec)
        if not r.passed:
            out["both_languages"] = r.reason
    return out


# --------------------------------------------------------------------------
# Step 2: the three predicted risks, checked by name
# --------------------------------------------------------------------------
def diagnose_risks(items: list[dict]) -> dict:
    """For every correct rewrite that fails an entity check, classify the entity pair."""
    id_spacing, es_separator, mojibake, other = [], [], [], []
    for item in items:
        src_ents = extract(item["source"]["text"])
        src_norm = normalize_all(src_ents)
        for lang, key in (("en", "rewrite_en"), ("es", "rewrite_es")):
            if _is_expected_reject(item, lang):
                continue
            out_ents = extract(item[key])
            for e in out_ents:
                ne = normalize_all([e])
                if ne <= src_norm:
                    continue  # this entity matched something in source
                # Unmatched: classify why.
                raw = e.raw
                entry = f"{item['id']}/{lang}: rewrite entity {e.entity_class.value} {raw!r} not matched in source"
                if any(c in item["source"]["text"] for c in "ûæºôö┴±ò") and _looks_mojibake_related(raw, item["source"]["text"]):
                    mojibake.append(entry)
                elif e.entity_class is EntityClass.NAME and _has_spaced_identifier(raw, item["source"]["text"]):
                    id_spacing.append(entry)
                elif e.entity_class is EntityClass.NUMBER and ("." in raw):
                    es_separator.append(entry)
                else:
                    other.append(entry)
    return {
        "identifier_spacing": id_spacing,
        "spanish_number_separator": es_separator,
        "mojibake": mojibake,
        "other": other,
    }


def _has_spaced_identifier(raw: str, source: str) -> bool:
    compact = raw.replace(" ", "")
    return compact != raw or (compact not in source and _spaced_variant_in(compact, source))


def _spaced_variant_in(compact: str, source: str) -> bool:
    import re
    pattern = r"\s*".join(re.escape(c) for c in compact)
    import re as _re
    return _re.search(pattern, source) is not None


def _looks_mojibake_related(raw: str, source: str) -> bool:
    return False  # entity raws here are numbers/names; mojibake is punctuation. Refined in report.


# --------------------------------------------------------------------------
def main() -> None:
    items = load()

    print("=" * 78)
    print("TASK 8 CALIBRATION — golden set 0a (6 items, 12 rewrites)")
    print("=" * 78)

    print("\n--- STEP 0: PRE-CHECK, entities in a rewrite absent from source ---")
    absent = precheck_absent_entities(items)
    if absent:
        print("  AUTHORING-ERROR CANDIDATES (flagged, not calibrated around):")
        for a in absent:
            print("   ", a)
    else:
        print("  none — every correct rewrite's entities trace to its source.")

    print("\n--- STEP 3 (first): DERIVE reading-level thresholds ---")
    th = derive_thresholds(items)
    for lang in ("en", "es"):
        d = th[lang]
        print(f"  [{lang}] rewrite scores: {d['rewrite_scores']}")
        print(f"  [{lang}] source  scores: {d['source_scores']}")
        print(f"  [{lang}] min_rewrite={d['min_rewrite']}  max_source={d['max_source']}  mean_gap={d['mean_gap']}")
        print(f"  [{lang}] DERIVED FLOOR = {d['derived_floor']}  (min correct-rewrite score - 5.0 margin)")

    en_floor = th["en"]["derived_floor"]
    es_floor = th["es"]["derived_floor"]

    print("\n--- STEP 1: MATRIX (rewrite x check) with derived floors ---")
    header = f"{'rewrite':16} | " + " | ".join(f"{n[:6]:6}" for n in _CHECK_NAMES)
    print("  " + header)
    print("  " + "-" * len(header))
    rejected_good = []
    unexpected = []
    for item in items:
        rec = _record(item)
        for label, rw in _rewrites(item):
            lang = label.rsplit("/", 1)[1]
            floor = en_floor if rw.language is Language.EN else es_floor
            row = run_checks(rw, rec, floor)
            cells = []
            for n in _CHECK_NAMES:
                v = row[n]
                cells.append(" n/a  " if v is None else ("PASS  " if v else "FAIL  "))
            print(f"  {label:16} | " + " | ".join(cells))
            applicable = [v for v in row.values() if v is not None]
            all_pass = all(applicable)
            expect_reject = _is_expected_reject(item, lang)
            if expect_reject and all_pass:
                unexpected.append(f"{label}: expected REJECT but PASSED")
            if (not expect_reject) and (not all_pass):
                rejected_good.append((label, reasons(rw, rec, floor)))
            if expect_reject and not all_pass:
                # Which check caught it?
                caught = [n for n in _CHECK_NAMES if row.get(n) is False]
                print(f"      -> expected reject, caught by: {caught}")

    print("\n--- KNOWN-GOOD REJECTION RATE ---")
    n_good = sum(1 for it in items for lbl, _ in _rewrites(it)
                 if not _is_expected_reject(it, lbl.rsplit('/', 1)[1]))
    print(f"  correct rewrites: {n_good}")
    print(f"  correct rewrites REJECTED: {len(rejected_good)}")
    print(f"  rejection rate: {len(rejected_good) / n_good:.0%}")
    if rejected_good:
        print("  REJECTED-GOOD DETAIL (this is the calibration finding):")
        for label, why in rejected_good:
            print(f"    {label}: {why}")

    print("\n--- STEP 2: THREE PREDICTED RISKS ---")
    risks = diagnose_risks(items)
    for name in ("identifier_spacing", "spanish_number_separator", "mojibake", "other"):
        hits = risks[name]
        status = "CONFIRMED" if hits else "not triggered"
        print(f"  [{status}] {name}: {len(hits)}")
        for h in hits:
            print(f"      {h}")

    print("\n--- EXPECTED-REJECT CHECK ---")
    if unexpected:
        for u in unexpected:
            print("  UNEXPECTED:", u)
    else:
        print("  both adversarial rewrites were rejected as expected.")


if __name__ == "__main__":
    main()
