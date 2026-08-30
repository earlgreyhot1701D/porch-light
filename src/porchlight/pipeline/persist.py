"""Porch Light — persist parent rows before the document loop (Spec 2).

The `documents` and `body_status` tables have FKs to `meetings` and `bodies`.
The pipeline must create those parent rows before writing children, or the
inserts violate the FK (the bug that reached the deployed hunter: DB tests had
pre-seeded parents in fixtures, so this step was never written — testing.md #4
now forbids seeding outputs).

Both upserts are idempotent, so a re-run or crash-restart re-applies them
harmlessly.
"""

from __future__ import annotations

from porchlight.adapters.ventura.registry import BODIES
from porchlight.log import get_logger

log = get_logger("porchlight.pipeline.persist")


def seed_bodies(backend) -> None:
    """Idempotently upsert the 21 registry bodies. Safe to call every run."""
    for b in BODIES:
        backend.execute(
            "INSERT INTO bodies (body_id, name_en, category) VALUES (%s, %s, %s) "
            "ON CONFLICT (body_id) DO UPDATE SET name_en = EXCLUDED.name_en, "
            "category = EXCLUDED.category",
            [b.body_id, b.name_en, b.category],
        )


def upsert_meetings(backend, stubs) -> int:
    """Idempotently upsert in-horizon meeting stubs. Returns the count.

    A stub with an unrecognized body (body_id None) is skipped for the FK's sake
    and surfaced — never fabricated into a body (registry rot point, R9.2). Its
    documents are not recorded this run; the unknown-body warning from enumerate
    already flagged it for review.
    """
    n = 0
    for s in stubs:
        if s.body_id is None:
            log.warning("meeting_skipped_unknown_body", meeting_id=s.meeting_id,
                        body_name_raw=s.body_name_raw)
            continue
        backend.execute(
            "INSERT INTO meetings (meeting_id, body_id, meeting_date, meeting_type, cancelled) "
            "VALUES (%s, %s, %s::date, %s, FALSE) "
            "ON CONFLICT (meeting_id) DO UPDATE SET meeting_date = EXCLUDED.meeting_date",
            [s.meeting_id, s.body_id, s.meeting_date.isoformat(), "unknown"],
        )
        n += 1
    return n
