"""Ventura adapter — data models.

Frozen dataclasses only. No behavior, no I/O. These are the structured records
the adapter hands to the storage boundary (Spec 2 owns the schema).

Vocabulary (§35a): Ventura publishes 2-to-14-page *agendas*, not packets. These
models use "document" and "agenda", never "packet".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class DocumentRole(str, Enum):
    """The deterministic role of a document (never model-decided, §model-authority).

    `UNCLASSIFIED` is a first-class outcome, not an error: when signals do not
    confidently indicate a role, we record it as unclassified and surface it for
    review rather than guess (R3.6, never.md #1).
    """

    AGENDA = "agenda"
    AMENDED_AGENDA = "amended_agenda"
    SUPPLEMENTAL = "supplemental"
    CANCELLATION = "cancellation"
    SPANISH_EDITION = "spanish_edition"
    MINUTES = "minutes"
    UNCLASSIFIED = "unclassified"


class MeetingType(str, Enum):
    """Meeting type, read from the agenda text, never inferred from the URL (R2)."""

    REGULAR = "regular"
    SPECIAL = "special"
    ADJOURNED = "adjourned"
    CLOSED_SESSION = "closed_session"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Body:
    """A public legislative or advisory body.

    The registry is a list of body identities, not URLs (R1): enumeration reads
    the single combined AgendaCenter index and attributes meetings to a body by
    the index grouping.
    """

    body_id: str
    """Stable identifier, e.g. 'city_council'."""

    name_en: str
    """Official English name exactly as the city renders it (copied, not paraphrased)."""

    category: str
    """'legislative' or 'advisory'."""


@dataclass(frozen=True)
class Document:
    """One file attached to a meeting.

    `document_id` is a content hash (R3.7) so identical bytes are always the same
    id and a re-post is idempotent.
    """

    document_id: str
    """Content hash of the document bytes."""

    url: str
    """Absolute URL on the permitted host (§34). Never a Granicus URL."""

    role: DocumentRole
    """Deterministic classification (classify.py)."""


@dataclass(frozen=True)
class Meeting:
    """One dated convening of a body, with its associated documents.

    `meeting_date` is authoritative from source text, never inferred from a file
    name or posting order (R2.4). `start_time_local` is the meeting start time
    parsed from the agenda text when available; None when it could not be parsed
    (surfacing then falls back to end-of-day and logs it, R5.4).
    """

    meeting_id: str
    """The city's stable meeting id from the URL segment."""

    body_id: str
    meeting_date: date
    meeting_type: MeetingType
    start_time_local: datetime | None
    """Meeting start datetime in city local time, or None if unparseable."""

    documents: tuple[Document, ...]
    """All documents for this meeting, including the version/supplemental trail."""

    cancelled: bool = False
    """True if a cancellation document was found for this meeting (R3.2)."""
