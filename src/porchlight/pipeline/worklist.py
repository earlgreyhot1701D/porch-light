"""Porch Light — in-process work list over in-horizon documents (Spec 2 R4).

The queue is a STUB by decision (§32c rigor budget: match the machinery to the
workload). This is an ordered in-process list, not a message queue.

    STUB (v2, not built): an SQS work queue with visibility timeout and a DLQ.
    Build it ONLY when one of these becomes true:
      (a) more than one city is ingested, or
      (b) a single run no longer fits in one process within T11.
    Until then, an in-process deterministically-ordered list plus the per-document
    DB status column (status.py) is correct and has fewer failure modes than a
    queue would introduce. The workload today is ~15 in-horizon meetings, ~35
    fetches, max 1 concurrent, finishing in ~90 seconds, in one process.

Deterministic ordering matters: a re-run (or a crash-restart) must visit documents
in the same order so behavior is reproducible and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class WorkItem:
    """One unit of ingestion work: a document to fetch/hash/record for a meeting."""

    meeting_id: str
    body_id: str | None
    meeting_date: date
    document_url: str
    role: str


# The permitted host (§34). AgendaCenter links in the index are relative
# (/AgendaCenter/...); the fetch layer requires absolute permitted-host URLs and
# blocks anything else, so we make them absolute here.
_PERMITTED_BASE = "https://www.cityofventura.ca.gov"


def _absolute(url: str) -> str:
    if url.startswith("http"):
        return url
    return _PERMITTED_BASE + url


def build_worklist(meeting_stubs) -> list[WorkItem]:
    """Flatten in-horizon meeting stubs into a deterministically ordered work list.

    Order: (meeting_date, meeting_id, document_url). Deterministic so re-runs and
    crash-restarts visit work in the same sequence (R4.1). The horizon gate has
    already been applied by the caller, so every stub here is in-window.
    Relative AgendaCenter URLs are made absolute against the permitted host.
    """
    items: list[WorkItem] = []
    for stub in meeting_stubs:
        for url in stub.document_urls:
            items.append(
                WorkItem(
                    meeting_id=stub.meeting_id,
                    body_id=stub.body_id,
                    meeting_date=stub.meeting_date,
                    document_url=_absolute(url),
                    role="",  # role is classified when the document is recorded (previous_versions/classify)
                )
            )
    items.sort(key=lambda w: (w.meeting_date, w.meeting_id, w.document_url))
    return items
