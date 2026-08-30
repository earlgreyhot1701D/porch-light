"""Porch Light — spend ledger (Spec 2 R6, §16a L5, §18b).

This ledger covers MODEL AND API SPEND ONLY. Aurora Serverless v2 fixed compute
(~$43/month at its 0.5-ACU floor) is INFRASTRUCTURE, tracked in §13's wind-down
list, and is NOT bounded by T15. If you are reading this at midnight in three
weeks: the $10 ceiling is not the monthly bill.

The ledger is checked BEFORE a run starts (§16a L5): when the sub-budget for the
month is spent, the run does not start — this is an application control, not a
cloud budget alert (which only emails). Ingestion and search are SEPARATE
sub-budgets of T15 so that search exhaustion cannot starve ingestion (§18b — the
availability-via-cost finding).
"""

from __future__ import annotations

from porchlight.pipeline.thresholds import (
    INGESTION_SUBBUDGET_USD,
    SEARCH_SUBBUDGET_USD,
)
from porchlight.log import get_logger

log = get_logger("porchlight.pipeline.ledger")

_SUBBUDGET = {
    "ingestion": INGESTION_SUBBUDGET_USD,
    "search": SEARCH_SUBBUDGET_USD,
}


class BudgetExhausted(Exception):
    """The component's monthly sub-budget is spent; the run does not start."""


def month_spend(backend, component: str) -> float:
    """Sum of this component's spend for the current calendar month (UTC)."""
    r = backend.query(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM spend_ledger "
        "WHERE component = %s AND date_trunc('month', ts) = date_trunc('month', now())",
        [component],
    )
    return float(r.rows[0]["total"]) if r.rows else 0.0


def check_before_run(backend, component: str = "ingestion") -> None:
    """Raise BudgetExhausted if the component's sub-budget for the month is spent.

    Called before a run starts (R6.1). Fails closed and loudly (log + raise), never
    silently degrades (never.md #7).
    """
    budget = _SUBBUDGET.get(component)
    if budget is None:
        raise ValueError(f"Unknown spend component '{component}'")
    spent = month_spend(backend, component)
    if spent >= budget:
        log.error("budget_exhausted", component=component, spent=spent, budget=budget)
        raise BudgetExhausted(
            f"{component} sub-budget spent this month (${spent:.4f} >= ${budget:.2f}); run will not start."
        )


def record(backend, run_id: str, cost_usd: float, component: str = "ingestion") -> None:
    """Append a spend row, attributable by run_id (R6.4).

    For rows with no model (ingestion/API spend). Model spend uses
    `record_model_spend` so the model id is attributable for the §27 comparison.
    """
    backend.execute(
        "INSERT INTO spend_ledger (run_id, component, cost_usd) VALUES (%s, %s, %s)",
        [run_id, component, cost_usd],
    )


def record_model_spend(
    backend,
    run_id: str,
    cost_usd: float,
    model_id: str,
    component: str = "ingestion",
) -> None:
    """Append a MODEL spend row, attributable by run_id AND model id (Spec 3 R9.1, §27).

    Model spend counts toward the same sub-budget as its component (extraction and
    rewrite are ingestion-side), so the T15 ceiling and the sub-budget check are
    unchanged. The model id is recorded on the row and emitted in the log event so
    a measurement run is attributable per model (the §27 cost-per-agenda number).
    Requires a model_id — an empty one is a bug (a model call with no attributable
    model defeats the comparison), so it fails loudly rather than silently.
    """
    if not model_id:
        raise ValueError("record_model_spend requires a model_id (§27 attribution)")
    backend.execute(
        "INSERT INTO spend_ledger (run_id, component, cost_usd, model_id) VALUES (%s, %s, %s, %s)",
        [run_id, component, cost_usd, model_id],
    )
    log.info(
        "model_spend_recorded",
        run_id=run_id,
        component=component,
        cost_usd=cost_usd,
        model_id=model_id,
    )
