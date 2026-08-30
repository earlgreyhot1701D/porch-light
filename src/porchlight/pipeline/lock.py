"""Porch Light — run lock (Spec 2, §20).

A DB-ROW lock, not an in-memory flag, so it survives process death and is visible
to the next scheduled trigger. This is the piece §20 has bitten twice: first the
deadlock (a lock with no TTL), then the heartbeat side-door (a stuck-but-alive run
refreshing its lock forever). Both are closed here:

- TTL: a dead run's lock expires at T12 and the next trigger reclaims it.
- Heartbeat CAPPED at acquired_at + T11: a stuck-but-alive run stops refreshing
  once it passes the run timeout, so its lock still expires at T12. The heartbeat
  can never keep a hung run's lock alive.

The lock takes a `Backend` (db.data_api) by injection, so it is storage-agnostic
and directly testable against local Postgres.

Statuses a run can end in: `ok`, `interrupted` (SIGTERM/reclaim), `timed_out`
(exceeded T11 while alive) — all distinct from `failed` (§20e, design correction).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from porchlight.pipeline.thresholds import T11_WHOLE_RUN, T12_LOCK_TTL
from porchlight.log import get_logger

log = get_logger("porchlight.pipeline.lock")

LOCK_NAME = "ingestion"


class LockNotAcquired(Exception):
    """Another live run holds the lock. The caller exits without starting."""


class RunTimedOut(Exception):
    """The run exceeded T11 wall-clock. Caller stops work and records `timed_out`."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunLock:
    """A held run lock with a T11-capped heartbeat.

    Use as a context manager:

        with RunLock.acquire(backend, run_id) as lock:
            for doc in worklist:
                lock.check_deadline()   # raises RunTimedOut past T11
                ...

    On exit, the lock is released. On SIGTERM the caller should catch it, mark the
    run `interrupted`, and let the context manager release.
    """

    backend: object  # db.data_api.Backend
    run_id: str
    acquired_at: datetime
    _stop: threading.Event
    _thread: threading.Thread | None = None

    # --- acquisition ---------------------------------------------------------

    @classmethod
    def acquire(cls, backend, run_id: str) -> "RunLock":
        """Acquire the lock, or raise LockNotAcquired if a live run holds it.

        Atomic take-or-fail: we delete any EXPIRED lock row first (heartbeat + ttl
        in the past), then insert ours. The insert's primary-key conflict is what
        makes this safe against a concurrent live holder — a live lock is never
        deleted, so the insert fails and we raise.
        """
        now = _utcnow()  # a real datetime; stringified only at the SQL boundary below.
        now_s = now.isoformat()
        # Reclaim a stale lock: one whose heartbeat + ttl has passed.
        # Timestamp params are cast explicitly (%s::timestamptz): the RDS Data API
        # does not implicitly cast text→timestamptz the way psycopg does, and the
        # cast is a no-op on the local path. (Backend-difference finding, §38 deploy.)
        backend.execute(
            "DELETE FROM run_lock WHERE lock_name = %s "
            "AND heartbeat_at + (ttl_seconds * interval '1 second') < %s::timestamptz",
            [LOCK_NAME, now_s],
        )
        try:
            backend.execute(
                "INSERT INTO run_lock (lock_name, run_id, acquired_at, heartbeat_at, ttl_seconds) "
                "VALUES (%s, %s, %s::timestamptz, %s::timestamptz, %s)",
                [LOCK_NAME, run_id, now_s, now_s, T12_LOCK_TTL],
            )
        except Exception as e:  # PK conflict = a live run holds it
            log.info("lock_not_acquired", run_id=run_id, error=type(e).__name__)
            raise LockNotAcquired(
                "A live run holds the ingestion lock; not starting."
            ) from e

        # acquired_at stays a real datetime so _deadline()/check_deadline() arithmetic works.
        lock = cls(backend=backend, run_id=run_id, acquired_at=now, _stop=threading.Event())
        lock._start_heartbeat()
        log.info("lock_acquired", run_id=run_id)
        return lock

    # --- heartbeat (capped at T11) -------------------------------------------

    def _deadline(self) -> datetime:
        """Wall-clock instant past which this run is over (acquired_at + T11)."""
        return self.acquired_at + timedelta(seconds=T11_WHOLE_RUN)

    def _start_heartbeat(self) -> None:
        interval = max(1, T12_LOCK_TTL // 3)

        def beat() -> None:
            while not self._stop.wait(interval):
                # THE §20 SIDE-DOOR FIX: stop refreshing once past T11, even though
                # this thread (and the process) may still be alive. A hung main
                # thread cannot keep the lock alive past the run deadline.
                if _utcnow() >= self._deadline():
                    log.warning("lock_heartbeat_capped", run_id=self.run_id)
                    return
                self.backend.execute(
                    "UPDATE run_lock SET heartbeat_at = %s::timestamptz WHERE lock_name = %s AND run_id = %s",
                    [_utcnow().isoformat(), LOCK_NAME, self.run_id],
                )

        self._thread = threading.Thread(target=beat, name="run-lock-heartbeat", daemon=True)
        self._thread.start()

    def check_deadline(self) -> None:
        """Raise RunTimedOut if the run has exceeded T11. Call between units of work."""
        if _utcnow() >= self._deadline():
            raise RunTimedOut(f"Run {self.run_id} exceeded T11 ({T11_WHOLE_RUN}s).")

    # --- release -------------------------------------------------------------

    def release(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.backend.execute(
            "DELETE FROM run_lock WHERE lock_name = %s AND run_id = %s",
            [LOCK_NAME, self.run_id],
        )
        log.info("lock_released", run_id=self.run_id)

    def __enter__(self) -> "RunLock":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def is_locked(backend) -> bool:
    """True iff a NON-expired lock row exists. For diagnostics/tests."""
    now = _utcnow().isoformat()
    r = backend.query(
        "SELECT run_id FROM run_lock WHERE lock_name = %s "
        "AND heartbeat_at + (ttl_seconds * interval '1 second') >= %s::timestamptz",
        [LOCK_NAME, now],
    )
    return r.row_count > 0
