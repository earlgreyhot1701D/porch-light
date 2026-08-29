"""Run-lock tests (Spec 2 task 2.2), including the stuck-but-alive case (§20).

These need a real Postgres (the lock is DB-row logic with interval arithmetic).
They skip cleanly when DATABASE_URL is unset, and fail on any error from a DB that
exists — the Spec 0 skip-vs-fail discipline.

The lock is the highest-risk piece in Spec 2: §20 has bitten twice (deadlock, then
the heartbeat side-door). The stuck-run test is the most valuable one here.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# db/ is not a package under porchlight; add it to the path for the backend seam.
sys.path.insert(0, str(Path(__file__).parent.parent / "db"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL unset: no database to test the run lock against.",
)

from porchlight.pipeline.lock import (  # noqa: E402
    LOCK_NAME,
    LockNotAcquired,
    RunLock,
    RunTimedOut,
    is_locked,
)
from porchlight.pipeline import thresholds  # noqa: E402


def _utcnow():
    return datetime.now(timezone.utc)


@pytest.fixture()
def backend():
    import data_api  # from db/

    be = data_api.get_backend()
    # Ensure schema exists and start from a clean lock table each test.
    be.execute(Path(__file__).parent.parent.joinpath("db", "schema.sql").read_text(encoding="utf-8"))
    be.execute("DELETE FROM run_lock WHERE lock_name = %s", [LOCK_NAME])
    yield be
    be.execute("DELETE FROM run_lock WHERE lock_name = %s", [LOCK_NAME])


def test_acquire_then_release(backend):
    lock = RunLock.acquire(backend, "run_a")
    assert is_locked(backend) is True
    lock.release()
    assert is_locked(backend) is False


def test_second_acquire_while_held_fails(backend):
    lock = RunLock.acquire(backend, "run_a")
    try:
        with pytest.raises(LockNotAcquired):
            RunLock.acquire(backend, "run_b")
    finally:
        lock.release()


def test_expired_lock_is_reclaimable(backend):
    """A dead run's lock (heartbeat + ttl in the past) is reclaimed by the next run."""
    # Insert a stale lock directly: heartbeat 20 min ago, ttl 15 min → expired.
    stale_hb = _utcnow() - timedelta(minutes=20)
    backend.execute(
        "INSERT INTO run_lock (lock_name, run_id, acquired_at, heartbeat_at, ttl_seconds) "
        "VALUES (%s, %s, %s, %s, %s)",
        [LOCK_NAME, "dead_run", stale_hb, stale_hb, thresholds.T12_LOCK_TTL],
    )
    assert is_locked(backend) is False  # stale, so not "locked"
    # A new run reclaims it.
    lock = RunLock.acquire(backend, "fresh_run")
    try:
        r = backend.query("SELECT run_id FROM run_lock WHERE lock_name = %s", [LOCK_NAME])
        assert r.rows[0]["run_id"] == "fresh_run"
    finally:
        lock.release()


def test_fresh_lock_is_not_reclaimable(backend):
    """A live lock (recent heartbeat) is NOT taken by another run."""
    fresh_hb = _utcnow()
    backend.execute(
        "INSERT INTO run_lock (lock_name, run_id, acquired_at, heartbeat_at, ttl_seconds) "
        "VALUES (%s, %s, %s, %s, %s)",
        [LOCK_NAME, "live_run", fresh_hb, fresh_hb, thresholds.T12_LOCK_TTL],
    )
    with pytest.raises(LockNotAcquired):
        RunLock.acquire(backend, "intruder")
    backend.execute("DELETE FROM run_lock WHERE lock_name = %s", [LOCK_NAME])


def test_ordering_invariant():
    """T11 < T12 < T14 — the §20 guard (§38 retired T16). Also asserted at import."""
    assert thresholds.T11_WHOLE_RUN < thresholds.T12_LOCK_TTL < thresholds.T14_SCHEDULE_INTERVAL


def test_stuck_but_alive_run_stops_extending_lock(backend):
    """THE §20 side-door case: a run past T11 must not keep its lock alive.

    We simulate a run that acquired the lock T11+1s ago (still 'alive'): its
    deadline has passed, so check_deadline() raises and the heartbeat would refuse
    to refresh. We then age the lock row past T12 and confirm it is reclaimable
    even though the 'process' never died.
    """
    lock = RunLock.acquire(backend, "stuck_run")
    try:
        # Force the run to look older than T11 by rewinding its acquired_at.
        lock.acquired_at = _utcnow() - timedelta(seconds=thresholds.T11_WHOLE_RUN + 1)
        # The run notices its deadline and would mark itself timed_out.
        with pytest.raises(RunTimedOut):
            lock.check_deadline()
        # The heartbeat is capped: past the deadline it will not refresh. Simulate
        # the DB row not having been refreshed and its heartbeat + ttl now in the
        # past (as it would be after T12 with no heartbeat).
        expired_hb = _utcnow() - timedelta(seconds=thresholds.T12_LOCK_TTL + 1)
        backend.execute(
            "UPDATE run_lock SET heartbeat_at = %s WHERE lock_name = %s AND run_id = %s",
            [expired_hb, LOCK_NAME, "stuck_run"],
        )
        # A new trigger reclaims the lock even though stuck_run never died.
        assert is_locked(backend) is False
        newlock = RunLock.acquire(backend, "recovered_run")
        newlock.release()
    finally:
        # stuck_run's context is abandoned; clean any residue.
        lock._stop.set()
