"""Porch Light — ingestion run entrypoint (Spec 2 R8, composes the pipeline).

Order (design §run-lifecycle):
  ledger check → lock (TTL+heartbeat) → fetch index → enumerate → horizon gate →
  worklist → per-doc record (conditional GET + hash upsert) with retry budget →
  circuit breaker → per-body last-read / quarantine → run log → ledger record →
  release lock.

No model call in Spec 2. The ledger + run log exist so Spec 3's model spend lands
in a ready, bounded envelope and every failure is traceable by run_id.

STUB (v2, §32c): SQS work queue with visibility timeout + DLQ. Build only when
(a) more than one city, or (b) a run no longer fits in one process within T11.
Until then the in-process ordered worklist (worklist.py) + per-document DB status
(status.py) is correct with fewer failure modes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from porchlight.adapters.ventura import fetch as vfetch
from porchlight.adapters.ventura.enumerate import enumerate_meetings
from porchlight.adapters.ventura.horizon import in_horizon
from porchlight.log import bind_context, generate_run_id, get_logger
from porchlight.pipeline import changedetect, ledger, persist, retry, runlog
from porchlight.pipeline.lock import LockNotAcquired, RunLock, RunTimedOut
from porchlight.pipeline.worklist import build_worklist

AGENDA_CENTER_URL = "https://www.cityofventura.ca.gov/AgendaCenter"


def run_ingestion(backend, *, index_url: str = AGENDA_CENTER_URL) -> str:
    """Execute one ingestion run. Returns the final readlog status.

    Fails closed: a degraded dependency produces an honest recorded status, never a
    fabricated result (never.md #7). Every failure path writes the run log and
    releases the lock.
    """
    run_id = generate_run_id()
    bind_context(component="hunter", run_id=run_id)
    log = get_logger("porchlight.pipeline.run")

    # L5: refuse to start if the ingestion sub-budget is spent.
    ledger.check_before_run(backend, "ingestion")

    try:
        lock = RunLock.acquire(backend, run_id)
    except LockNotAcquired:
        log.info("run_skipped_locked", run_id=run_id)
        return "skipped_locked"

    started = datetime.now(timezone.utc)
    runlog.start_run(backend, run_id, started)
    read = skipped = failed = quarantined = 0
    status = runlog.RUN_OK

    try:
        # Enumerate meetings from the combined index (1 fetch), then horizon-gate
        # BEFORE any per-meeting fetch so out-of-window meetings cost nothing.
        index = vfetch.fetch(index_url)
        stubs = enumerate_meetings(index.body.decode("utf-8") if index.body else "")
        in_window = [s for s in stubs if in_horizon(s.meeting_date)]

        # Persist parent rows BEFORE the document loop: documents/body_status FK to
        # meetings/bodies. Idempotent upserts (persist.py). Stubs with an unknown
        # body are dropped here and not worked (their FK would fail); enumerate
        # already surfaced the unknown body.
        persist.seed_bodies(backend)
        persist.upsert_meetings(backend, in_window)
        known = [s for s in in_window if s.body_id is not None]
        worklist = build_worklist(known)

        attempted = 0
        touched_bodies: set[str] = set()
        failed_bodies: set[str] = set()

        for item in worklist:
            lock.check_deadline()  # raises RunTimedOut past T11 (§20 side-door)
            attempted += 1
            try:
                outcome = changedetect.record_document(
                    backend, item.document_url, item.meeting_id, item.role, run_id
                )
                if outcome.changed:
                    read += 1
                elif outcome.unchanged:
                    skipped += 1
                if item.body_id:
                    touched_bodies.add(item.body_id)
            except Exception as e:  # noqa: BLE001 - classify, count, never swallow
                failed += 1
                if item.body_id:
                    failed_bodies.add(item.body_id)
                kind = retry.classify_failure(type(e).__name__ + ":" + str(e))
                log.error("doc_failed", url=item.document_url, kind=kind.value,
                          error=type(e).__name__)

            # L3 circuit breaker: stop the run if too many docs fail.
            if retry.circuit_broken(failed, attempted):
                status = runlog.RUN_CIRCUIT_BROKEN
                log.error("circuit_broken", failed=failed, attempted=attempted)
                break

        # Per-body last-read (success) / consecutive-fail + quarantine (L4).
        for body_id in touched_bodies - failed_bodies:
            runlog.mark_body_read(backend, body_id, datetime.now(timezone.utc))
        for body_id in failed_bodies:
            consecutive = runlog.mark_body_failed(backend, body_id)
            if retry.should_quarantine(consecutive):
                runlog.mark_body_quarantined(backend, body_id)
                quarantined += 1

    except RunTimedOut:
        status = runlog.RUN_TIMED_OUT
        log.error("run_timed_out", run_id=run_id)
    except ledger.BudgetExhausted:
        status = runlog.RUN_BUDGET_HALTED
        raise
    except Exception as e:  # noqa: BLE001 - fail closed, record honestly
        import traceback
        status = runlog.RUN_INTERRUPTED
        log.error("run_error", run_id=run_id, error=type(e).__name__, detail=str(e)[:300],
                  where=traceback.format_exc().splitlines()[-3:])
    finally:
        runlog.finish_run(
            backend, run_id, datetime.now(timezone.utc), status,
            read=read, skipped=skipped, failed=failed, quarantined=quarantined,
            cost_usd=0.0,  # no model spend in Spec 2; Spec 3 records real cost
        )
        ledger.record(backend, run_id, 0.0, "ingestion")
        lock.release()

    log.info("run_complete", run_id=run_id, status=status, read=read, skipped=skipped, failed=failed)
    return status
