"""Reading level — per language, never one metric applied to both (design R3b).

Pure functions over text, no I/O, no model. Uses `textstat` (pinned in
pyproject), which carries both an English metric (Flesch Reading Ease) and a
Spanish one (Fernandez Huerta) — so we do not apply an English-calibrated number
to Spanish, which would be a confident wrong answer (R3b, correction #2).

Both metrics score HIGHER = easier to read. Thresholds are NOT set here: they are
parameters, DERIVED from the golden set in task 8 (the reading scores of the
hand-written correct rewrites vs their sources). Guessing a threshold here would
be the exact "TBD-at-build" the calibration step exists to replace, so this
module only computes scores and compares against a passed-in floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import textstat


class Language(str, Enum):
    EN = "en"
    ES = "es"


@dataclass(frozen=True)
class ReadingScore:
    """A reading-ease score and the metric that produced it."""

    language: Language
    metric: str
    score: float


def score(text: str, language: Language) -> ReadingScore:
    """Compute the reading-ease score for text in its language.

    English -> Flesch Reading Ease. Spanish -> Fernandez Huerta (the Spanish
    analogue textstat ships). Higher is easier for both.

    Never raises: unscoreable input (empty/degenerate) returns score 0.0, which
    is the hardest-to-read end and will fail any sane floor — failing safe, not
    silently passing.
    """
    try:
        text = text or ""
        if not text.strip():
            return ReadingScore(language, _metric_name(language), 0.0)
        textstat.set_lang(language.value)
        if language is Language.ES:
            value = float(textstat.fernandez_huerta(text))
        else:
            value = float(textstat.flesch_reading_ease(text))
        return ReadingScore(language, _metric_name(language), value)
    except Exception:
        return ReadingScore(language, _metric_name(language), 0.0)


def _metric_name(language: Language) -> str:
    return "fernandez_huerta" if language is Language.ES else "flesch_reading_ease"


def passes(text: str, language: Language, floor: float) -> bool:
    """True if text reads at or above the per-language floor.

    `floor` is derived from the golden set in task 8, never hardcoded here. A
    higher score is easier, so passing means score >= floor.
    """
    return score(text, language).score >= floor
