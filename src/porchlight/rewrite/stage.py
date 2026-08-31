"""The rewrite stage (Spec 3 W4-W5): rewrite + verify + persist a document's items,
under the run's budget, with cost + observability on the real path.

W4 (cost/observability): a sub-budget check gates the stage (never-fail-open: if
the budget is spent the stage HALTS honestly, it does not skip verification and
ship unverified text); every model call's cost is recorded by run_id + model id;
model id is in every structured log event; the per-item verify outcome is logged.

W5 (wiring): `run_rewrite_stage` runs over the items already recorded for a
changed document. City-published-Spanish (§36b) short-circuits the ES chain for a
meeting matched on body_id + meeting date — our machine Spanish is not shown next
to a link to the city's own Spanish edition.

Kept out of the Spec-2 pipeline module (no refactor there): this is a new stage the
pipeline will call after extraction. Offline-testable with a fake client + backend.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from porchlight.log import get_logger
from porchlight.pipeline import ledger
from porchlight.rewrite import model as rewrite_model
from porchlight.rewrite.persist_rewrites import persist_item_rewrite
from porchlight.rewrite.pipeline import ItemRewriteResult, rewrite_item
from porchlight.verify import checks
from porchlight.verify.models import Language, Rewrite, SourceRecord

log = get_logger("porchlight.rewrite.stage")

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")


@dataclass(frozen=True)
class StageSummary:
    """What the stage did: counts for the run log + the write-up (retry/coverage)."""

    items: int
    en_verified: int
    es_verified: int
    en_fallback: int
    es_fallback: int
    es_recovered_on_retry: int
    body_unnamed: int
    cost_usd: float


def run_rewrite_stage(
    backend,
    run_id: str,
    items: list[tuple[str, SourceRecord]],
    *,
    model_id: str = MODEL_ID,
    client=None,
    city_spanish_meetings: frozenset[str] = frozenset(),
) -> StageSummary:
    """Rewrite + verify + persist every item for a changed document.

    Args:
        items: list of (item_id, SourceRecord) already recorded by the extractor.
        city_spanish_meetings: set of "body_id|meeting_date" keys that have a
            city-published Spanish edition (§36b); the ES chain is skipped for those.

    Never-fail-open: checks the ingestion sub-budget first; if spent, HALTS (raises
    BudgetExhausted) rather than shipping unverified text. Each item is always
    persisted with an honest per-language outcome.
    """
    # W4: budget gate before spending. Halt honestly, never skip verification.
    ledger.check_before_run(backend, "ingestion")

    en_verified = es_verified = en_fallback = es_fallback = es_recovered = body_unnamed = 0
    total_cost = 0.0

    # Cost is measured by wrapping the client so every Converse call's cost lands
    # in the ledger by run_id + model id (W4). We tally here and record once.
    counting = _CostCountingClient(client or rewrite_model.boto3.client("bedrock-runtime"), model_id)

    for item_id, source in items:
        key = f"{source.body}|{source.meeting_date}"
        skip_es = key in city_spanish_meetings
        result = _rewrite_one(source, model_id, counting, skip_es)

        if result.en_verified:
            en_verified += 1
        else:
            en_fallback += 1
        if result.es_verified:
            es_verified += 1
            if result.es_attempts == 2:
                es_recovered += 1
        elif not skip_es:
            es_fallback += 1

        # body_unnamed (v1: reported, not rejected): does the shown English name the
        # record's own body? Only meaningful when EN verified (a fallback shows the
        # original staff text, which does name the body).
        if result.en_verified and not checks.body_is_named(
            Rewrite(Language.EN, result.en_text), source
        ):
            body_unnamed += 1

        persist_item_rewrite(backend, item_id, run_id, model_id, result)

    total_cost = counting.total_cost
    if total_cost > 0:
        ledger.record_model_spend(backend, run_id, total_cost, model_id, "ingestion")

    summary = StageSummary(
        items=len(items), en_verified=en_verified, es_verified=es_verified,
        en_fallback=en_fallback, es_fallback=es_fallback,
        es_recovered_on_retry=es_recovered, body_unnamed=body_unnamed, cost_usd=total_cost,
    )
    log.info("rewrite_stage_done", run_id=run_id, model_id=model_id,
             items=summary.items, en_verified=en_verified, es_verified=es_verified,
             en_fallback=en_fallback, es_fallback=es_fallback,
             es_recovered_on_retry=es_recovered, body_unnamed=body_unnamed, cost_usd=total_cost)
    return summary


def _rewrite_one(source: SourceRecord, model_id: str, client, skip_es: bool) -> ItemRewriteResult:
    """Rewrite one item; §36b skip means we do NOT machine-translate to Spanish."""
    result = rewrite_item(source, model_id=model_id, client=client)
    if skip_es and result.es_verified:
        # City has its own Spanish edition (§36b): do not show our machine Spanish.
        return ItemRewriteResult(
            source=result.source, en_text=result.en_text, en_verified=result.en_verified,
            es_text=None, es_verified=False,
            en_attempts=result.en_attempts, es_attempts=0,
            note_en=result.note_en,
            es_absent_note=(
                "Spanish is available in the city's own published Spanish edition. "
                "El espa\u00f1ol est\u00e1 disponible en la edici\u00f3n en espa\u00f1ol publicada por la ciudad."
            ),
        )
    return result


class _CostCountingClient:
    """Wraps a bedrock-runtime client to sum Converse cost by model id (W4)."""

    def __init__(self, inner, model_id: str) -> None:
        self._inner = inner
        self._model_id = model_id
        self.total_cost = 0.0

    def converse(self, **kwargs):
        resp = self._inner.converse(**kwargs)
        usage = resp.get("usage", {})
        in_tok = int(usage.get("inputTokens", 0))
        out_tok = int(usage.get("outputTokens", 0))
        in_p, out_p = rewrite_model._price_for(self._model_id)
        self.total_cost += in_tok * in_p + out_tok * out_p
        return resp
