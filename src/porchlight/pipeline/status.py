"""Porch Light — per-document status transitions (Spec 2 R4).

The document `status` column drives the in-process work list and, with content-hash
idempotency (R3), makes a crashed-and-restarted run resume rather than repeat:

    pending → in_flight → done
                       ↘ parked          (transient failure, auto-retry next run)
                       ↘ permanent_fail  (never auto-retried; needs a human/code change)

Transitions are the ONLY way status changes, so an illegal jump (e.g. done→pending)
is caught here rather than corrupting the work list. All writes go through the
injected backend; the status write happens in the same logical step as the work
that caused it (R3.3), so a restart sees a coherent state.
"""

from __future__ import annotations

from enum import Enum


class DocStatus(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DONE = "done"
    PARKED = "parked"           # transient, auto-retried next run
    PERMANENT_FAIL = "permanent_fail"  # never auto-retried


# Legal transitions. A restart re-drives in_flight (idempotent via hash upsert);
# parked returns to pending on the next run; permanent_fail is terminal until a
# human clears it.
_ALLOWED: dict[DocStatus, set[DocStatus]] = {
    DocStatus.PENDING: {DocStatus.IN_FLIGHT},
    DocStatus.IN_FLIGHT: {DocStatus.DONE, DocStatus.PARKED, DocStatus.PERMANENT_FAIL, DocStatus.IN_FLIGHT},
    DocStatus.PARKED: {DocStatus.PENDING},  # next run re-queues it
    DocStatus.DONE: set(),                  # terminal for this content hash
    DocStatus.PERMANENT_FAIL: set(),        # terminal until human clears
}


class IllegalTransition(Exception):
    """Raised on a status jump not in the transition table (a bug, surfaced not hidden)."""


def can_transition(current: DocStatus, target: DocStatus) -> bool:
    return target in _ALLOWED.get(current, set())


def set_status(backend, document_id: str, current: DocStatus, target: DocStatus,
               fail_reason: str | None = None) -> None:
    """Move a document's status, guarding against illegal transitions.

    `fail_reason` is attached on parked/permanent_fail. It is stored for the run
    log and diagnostics; it is NEVER rendered as "late/overdue/failed" (§16b).
    """
    if not can_transition(current, target):
        raise IllegalTransition(f"{document_id}: {current.value} -> {target.value} not allowed")
    backend.execute(
        "UPDATE documents SET status = %s, fail_reason = %s, updated_at = now() WHERE document_id = %s",
        [target.value, fail_reason, document_id],
    )
