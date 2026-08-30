"""Porch Light — run log and per-body status (Spec 2 R7, §16c, §17).

Produces the DATA the public reading log (Spec 6) renders: one readlog row per
run (counts + cost + status) and per-body last-read timestamps. A single global
last-read timestamp is BANNED (R7.4, §16b) — it hides exactly the failure a
watcher needs to see, so last-read lives per body in body_status.

Absence and quarantine are never phrased as "late/overdue/failed" (never.md #3);
this module only records facts (timestamps, counts, a status enum), and the
rendering layer applies the §16b language.
"""

from __future__ import annotations

from porchlight.log import get_logger

log = get_logger("porchlight.pipeline.runlog")

# readlog.status values (mirror the schema CHECK constraint).
RUN_RUNNING = "running"
RUN_OK = "ok"
RUN_INTERRUPTED = "interrupted"     # SIGTERM / reclaim (§20e)
RUN_TIMED_OUT = "timed_out"         # exceeded T11 while alive (§20 side-door)
RUN_CIRCUIT_BROKEN = "circuit_broken"
RUN_BUDGET_HALTED = "budget_halted"


def start_run(backend, run_id: str, started_at) -> None:
    backend.execute(
        "INSERT INTO readlog (run_id, started_at, status) VALUES (%s, %s::timestamptz, %s)",
        [run_id, started_at.isoformat() if hasattr(started_at, "isoformat") else started_at, RUN_RUNNING],
    )


def finish_run(backend, run_id: str, finished_at, status: str,
               read: int, skipped: int, failed: int, quarantined: int, cost_usd: float) -> None:
    backend.execute(
        "UPDATE readlog SET finished_at = %s::timestamptz, status = %s, read_count = %s, skipped_count = %s, "
        "failed_count = %s, quarantined_count = %s, cost_usd = %s WHERE run_id = %s",
        [finished_at.isoformat() if hasattr(finished_at, "isoformat") else finished_at,
         status, read, skipped, failed, quarantined, cost_usd, run_id],
    )
    log.info("run_finished", run_id=run_id, status=status, read=read, skipped=skipped,
             failed=failed, quarantined=quarantined, cost_usd=cost_usd)


def mark_body_read(backend, body_id: str, read_at) -> None:
    """Record a SUCCESSFUL read of a body; reset its consecutive-fail counter."""
    backend.execute(
        "INSERT INTO body_status (body_id, last_read_at, consecutive_fails, quarantined) "
        "VALUES (%s, %s::timestamptz, 0, FALSE) "
        "ON CONFLICT (body_id) DO UPDATE SET last_read_at = EXCLUDED.last_read_at, "
        "consecutive_fails = 0, quarantined = FALSE",
        [body_id, read_at.isoformat() if hasattr(read_at, "isoformat") else read_at],
    )


def mark_body_failed(backend, body_id: str) -> int:
    """Increment a body's consecutive-fail counter; return the new count.

    The caller applies the quarantine decision (retry.should_quarantine) and sets
    quarantined via mark_body_quarantined. This only counts.
    """
    backend.execute(
        "INSERT INTO body_status (body_id, consecutive_fails) VALUES (%s, 1) "
        "ON CONFLICT (body_id) DO UPDATE SET consecutive_fails = body_status.consecutive_fails + 1",
        [body_id],
    )
    r = backend.query("SELECT consecutive_fails FROM body_status WHERE body_id = %s", [body_id])
    return int(r.rows[0]["consecutive_fails"])


def mark_body_quarantined(backend, body_id: str) -> None:
    backend.execute(
        "UPDATE body_status SET quarantined = TRUE WHERE body_id = %s", [body_id]
    )
    log.warning("body_quarantined", body_id=body_id)
