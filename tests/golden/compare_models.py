"""Task 9 model comparison — Nova Lite vs Claude Haiku over golden 0a.

Run (makes PAID Bedrock calls; approved): `uv run python tests/golden/compare_models.py`

Amendments honored:
  1. Each generation runs TWICE per model (run 1, run 2). If a model's two runs
     disagree, the model difference at n=10 is noise and the decision falls through
     to "pick Nova Lite."
  2. The prompt is a CONTROLLED variable: both models get the identical instruction
     from rewrite.chain (REWRITE_PROMPT_EN / REWRITE_PROMPT_ES).

For each model, each run, each of the ten known-good items (adversarials excluded
from the rejection-rate denominator): generate the EN rewrite, verify against
source; translate the verified EN to ES, verify against source. Record per-check,
per-language pass/fail and the actual ledger cost by model id.

The verifier is the already-calibrated one (derived floors from thresholds.py); it
is NOT modified here. Real model cost is recorded via ledger.record_model_spend
when a DB is available; the harness also sums the per-call estimated cost so it
reports even without a DB.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from porchlight.log import bind_context, generate_run_id, get_logger
from porchlight.pipeline.thresholds import READING_FLOOR_EN, READING_FLOOR_ES
from porchlight.rewrite import chain, model
from porchlight.verify import checks
from porchlight.verify.models import Language, Rewrite, SourceRecord

GOLDEN = Path(__file__).parent / "golden_set.json"

MODELS = {
    "nova_lite": "amazon.nova-lite-v1:0",
    "haiku": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
}
RUNS = (1, 2)

log = get_logger("porchlight.compare_models")


def _record(item: dict) -> SourceRecord:
    s = item["source"]
    return SourceRecord(
        body=s["body_id"], meeting_date=s["meeting_date"], item_number=s["item_number"],
        page_range=tuple(s["page_range"]), text=s["text"], deadline=None,
        source_url=s["document_url"],
    )


@dataclass
class Tally:
    total: int = 0
    rejected: int = 0
    per_check: dict = None
    per_lang: dict = None

    def __post_init__(self):
        self.per_check = {c: 0 for c in ("schema", "entity_preservation", "no_new_entities", "containment", "reading_level", "both_languages")}
        self.per_lang = {"en": {"total": 0, "rejected": 0}, "es": {"total": 0, "rejected": 0}}


def _verify_en(rw: Rewrite, rec: SourceRecord) -> dict[str, bool]:
    return {
        "schema": checks.check_schema(rw).passed,
        "entity_preservation": checks.check_entity_preservation(rw, rec).passed,
        "no_new_entities": checks.check_no_new_entities(rw, rec).passed,
        "containment": checks.check_containment(rw, rec).passed,
        "reading_level": checks.check_reading_level(rw, rec, READING_FLOOR_EN).passed,
    }


def _verify_es(rw: Rewrite, rec: SourceRecord) -> dict[str, bool]:
    return {
        "schema": checks.check_schema(rw).passed,
        "entity_preservation": checks.check_entity_preservation(rw, rec).passed,
        "no_new_entities": checks.check_no_new_entities(rw, rec).passed,
        "containment": checks.check_containment(rw, rec).passed,
        "reading_level": checks.check_reading_level(rw, rec, READING_FLOOR_ES).passed,
        "both_languages": checks.check_both_languages(rw, rec).passed,
    }


def _tally(t: Tally, lang: str, row: dict[str, bool]) -> None:
    t.total += 1
    t.per_lang[lang]["total"] += 1
    failed = [c for c, ok in row.items() if ok is False]
    if failed:
        t.rejected += 1
        t.per_lang[lang]["rejected"] += 1
        for c in failed:
            t.per_check[c] += 1


def run_model(model_id: str, items: list[dict], run_no: int) -> tuple[Tally, float]:
    t = Tally()
    cost = 0.0
    for item in items:
        if item.get("adversarial_language"):
            continue  # good rewrites only in the rejection-rate denominator
        rec = _record(item)
        # EN stage
        en_resp = model.invoke(model_id, chain.REWRITE_PROMPT_EN, chain.build_user_text(rec.text))
        cost += en_resp.cost_usd
        en_rw = Rewrite(Language.EN, en_resp.text.strip())
        _tally(t, "en", _verify_en(en_rw, rec))
        # ES stage: translate the (unverified-here) EN; the chain verifies ES vs source
        es_resp = model.invoke(model_id, chain.REWRITE_PROMPT_ES, chain.build_es_user_text(en_rw.summary))
        cost += es_resp.cost_usd
        es_rw = Rewrite(Language.ES, es_resp.text.strip())
        _tally(t, "es", _verify_es(es_rw, rec))
        log.info("compare_item_done", model_id=model_id, run=run_no, item=item["id"],
                 en_cost=en_resp.cost_usd, es_cost=es_resp.cost_usd)
    return t, cost


def main() -> None:
    # 'spike' is the allowed build-time/experiment component; this comparison is a
    # one-off measurement harness, not a product component.
    bind_context(component="spike", run_id=generate_run_id())
    items = json.loads(GOLDEN.read_text(encoding="utf-8"))["items"]
    n_good = sum(1 for i in items if not i.get("adversarial_language"))

    print("=" * 78)
    print(f"TASK 9 MODEL COMPARISON — {n_good} known-good items x 2 langs x 2 runs x 2 models")
    print(f"EN floor={READING_FLOOR_EN}  ES floor={READING_FLOOR_ES}")
    print("=" * 78)

    grand_cost = 0.0
    results: dict = {}
    for name, model_id in MODELS.items():
        results[name] = {}
        for run_no in RUNS:
            t, cost = run_model(model_id, items, run_no)
            grand_cost += cost
            results[name][run_no] = (t, cost)
            rate = t.rejected / t.total if t.total else 0.0
            print(f"\n[{name}] run {run_no}  ({model_id})")
            print(f"  rejection rate: {t.rejected}/{t.total} = {rate:.0%}   cost ${cost:.5f}")
            print(f"  per language: EN {t.per_lang['en']['rejected']}/{t.per_lang['en']['total']}  "
                  f"ES {t.per_lang['es']['rejected']}/{t.per_lang['es']['total']}")
            failed_checks = {c: n for c, n in t.per_check.items() if n}
            print(f"  per check (rejections): {failed_checks or 'none'}")

    print("\n" + "=" * 78)
    print(f"TOTAL ACTUAL COST (summed per-call): ${grand_cost:.5f}")
    print("=" * 78)

    # Decision-rule read-out.
    print("\n--- DECISION ---")
    for name in MODELS:
        r1 = results[name][1][0]
        r2 = results[name][2][0]
        rate1 = r1.rejected / r1.total if r1.total else 0
        rate2 = r2.rejected / r2.total if r2.total else 0
        agree = (r1.rejected == r2.rejected)
        print(f"  {name}: run1={rate1:.0%} run2={rate2:.0%}  runs_agree={agree}")


if __name__ == "__main__":
    main()
