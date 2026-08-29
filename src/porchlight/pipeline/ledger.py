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
    """Append a spend row, attributable by run_id (R6.4)."""
    backend.execute(
        "INSERT INTO spend_ledger (run_id, component, cost_usd) VALUES (%s, %s, %s)",
        [run_id, component, cost_usd],
    )
