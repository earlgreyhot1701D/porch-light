"""Rewrite pipeline wiring (Spec 3 W1-W2): compose the model into the verifier,
and apply the per-language never-fail-open fallback (design.md).

This module contains NO new model logic and NO new verifier logic. It binds the
existing pieces:
  - `rewrite.chain` controlled prompts + `rewrite.model.invoke` (Nova Lite, config)
    -> the `rewrite_fn` shape `verify.verifier.verify_with_retry` expects (W1).
  - two INDEPENDENT verify-with-retry passes, EN then ES, so the languages fall
    back independently (W2): EN can verify while ES does not.

Per-language fallback (design.md, never.md #7 — never fail open):
  - EN fails twice   -> show original English staff text + note; never the unverified rewrite.
  - ES fails twice   -> emit the VERIFIED English + a note that verified Spanish was
                        not produced for this item; never the unverified ES; never drop.
  - The item is ALWAYS present, always with an honest statement of what verified.
Model is Nova Lite for attempt AND retry (no silent provider fallback).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from porchlight.pipeline.thresholds import READING_FLOOR_EN, READING_FLOOR_ES
from porchlight.rewrite import chain, model
from porchlight.verify.models import Language, Rewrite, SourceRecord
from porchlight.verify.verifier import RewriteOutcome, verify_with_retry

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")


# --- W1: compose the model into rewrite_fn closures ---

def make_en_rewrite_fn(model_id: str, client=None):
    """Return a rewrite_fn(source, failure_reason) -> Rewrite for the EN stage.

    The controlled EN prompt is fixed; on a retry the failure reason is appended so
    the model knows what to fix (a retry is code deciding after checking, not a loop).
    """
    def _fn(source: SourceRecord, failure_reason: str) -> Rewrite:
        user = chain.build_user_text(source.text)
        if failure_reason:
            user += f"\n\n(Your previous attempt was rejected: {failure_reason}. Fix it.)"
        resp = model.invoke(model_id, chain.REWRITE_PROMPT_EN, user, client=client)
        return Rewrite(Language.EN, resp.text.strip())

    return _fn


def make_es_rewrite_fn(model_id: str, verified_en: str, client=None):
    """Return a rewrite_fn for the ES stage, translating the VERIFIED English (§21a).

    Bound to the already-verified EN text; the ES chain hop translates that, and the
    verifier checks the ES against the ORIGINAL source (not the EN).
    """
    def _fn(source: SourceRecord, failure_reason: str) -> Rewrite:
        user = chain.build_es_user_text(verified_en)
        if failure_reason:
            user += f"\n\n(Su intento anterior fue rechazado: {failure_reason}. Corrijalo.)"
        resp = model.invoke(model_id, chain.REWRITE_PROMPT_ES, user, client=client)
        return Rewrite(Language.ES, resp.text.strip())

    return _fn


# --- W2: per-language fallback result ---

@dataclass(frozen=True)
class ItemRewriteResult:
    """The end state of one item after the EN and ES passes, independently.

    The item is ALWAYS present. `en_text` is the verified EN rewrite, or the
    original English staff text when EN failed twice (`en_verified` False).
    `es_text` is the verified ES rewrite, or None when ES failed twice
    (`es_verified` False) — in which case the reader is shown the verified English
    with `es_absent_note`. Never carries an unverified rewrite.
    """

    source: SourceRecord
    en_text: str
    en_verified: bool
    es_text: str | None
    es_verified: bool
    en_attempts: int
    es_attempts: int
    note_en: str = ""
    es_absent_note: str = ""

    @property
    def shown_english(self) -> str:
        """What the reader sees in English (verified rewrite, or original staff text)."""
        return self.en_text


_EN_FALLBACK_NOTE = (
    "A verified plain-English summary could not be produced for this item; "
    "showing the original text as published by the city."
)
_ES_ABSENT_NOTE = (
    "A verified Spanish version was not produced for this item. "
    "No se pudo producir una versi\u00f3n verificada en espa\u00f1ol para este punto."
)


def rewrite_item(
    source: SourceRecord,
    *,
    model_id: str = MODEL_ID,
    client=None,
) -> ItemRewriteResult:
    """Run the full per-item rewrite: EN pass, then ES pass, with independent fallback.

    Never raises the model's errors to the caller and never emits an unverified
    rewrite or drops the item (never-fail-open). Uses Nova Lite (from config) for
    both the attempt and the retry.
    """
    # EN pass.
    en_outcome: RewriteOutcome = verify_with_retry(
        source, READING_FLOOR_EN, make_en_rewrite_fn(model_id, client), Language.EN
    )
    if en_outcome.shown_original:
        # EN failed twice: show original English staff text; ES cannot be produced
        # from a verified EN, so ES is also absent (honest, not fabricated).
        return ItemRewriteResult(
            source=source,
            en_text=source.text,
            en_verified=False,
            es_text=None,
            es_verified=False,
            en_attempts=en_outcome.attempts,
            es_attempts=0,
            note_en=_EN_FALLBACK_NOTE,
            es_absent_note=_ES_ABSENT_NOTE,
        )

    verified_en = en_outcome.final.summary  # type: ignore[union-attr]

    # ES pass: translate the verified EN, verify ES against the ORIGINAL source.
    es_outcome: RewriteOutcome = verify_with_retry(
        source, READING_FLOOR_ES, make_es_rewrite_fn(model_id, verified_en, client),
        Language.ES,
    )
    if es_outcome.shown_original:
        return ItemRewriteResult(
            source=source, en_text=verified_en, en_verified=True,
            es_text=None, es_verified=False,
            en_attempts=en_outcome.attempts, es_attempts=es_outcome.attempts,
            es_absent_note=_ES_ABSENT_NOTE,
        )

    return ItemRewriteResult(
        source=source, en_text=verified_en, en_verified=True,
        es_text=es_outcome.final.summary, es_verified=True,  # type: ignore[union-attr]
        en_attempts=en_outcome.attempts, es_attempts=es_outcome.attempts,
    )
