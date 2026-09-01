"""Watcher user-facing strings — bilingual by construction (R3.4, R9, voice.md).

Every string here exists in English AND Spanish, equal weight. These are the
watcher-produced strings the Spec 6 surface renders (correct `lang` attributes are
the renderer's concern; the values live here).

LOAD-BEARING, VERBATIM (voice.md — do not "improve"):
  - PRIVACY: the exact approved wording. It replaced an older claim that we do not
    observe the transmitted list, which became untrue once the watcher matches from a
    transmitted watchlist (voice.md §26c note). Do NOT revert it, and no string here
    may claim the transmitted list is unobserved.
  - GREETING_ES is provisionally "Buenas tardes, vecindad." pending fluent review.

Spanish is checked for gendered second-person and role nouns (voice.md: English can
be gender-neutral by accident, Spanish cannot). "vecindad" (neighborhood) is used as
a gender-neutral address rather than "vecinos/vecinas". Pending fluent review is
noted in KNOWN-LIMITATIONS.
"""

from __future__ import annotations

from porchlight.web.contract import Bilingual

# Verbatim, non-negotiable (voice.md). Byte-for-byte the approved wording.
PRIVACY = Bilingual(
    en="Your list stays on your device. We use it to answer, and never store it.",
    es="Tu lista permanece en tu dispositivo. La usamos para responder y nunca la guardamos.",
)

# The quiet week is the product working, not failing — a complete, calm answer.
QUIET_WEEK = Bilingual(
    en="Nothing new for you this week.",
    es="Nada nuevo para ti esta semana.",
)

# Honest degraded state — distinct from quiet, says we could not fully look.
DEGRADED = Bilingual(
    en="We could not fully check your list right now. This is not an all-clear.",
    es="No pudimos revisar tu lista por completo en este momento. Esto no es una confirmacion de que no haya nada.",
)

# Partial (a cap fired): matches shown are real; some items were not reached.
PARTIAL = Bilingual(
    en="Some items were not checked (a limit was reached). Showing what was found.",
    es="Algunos puntos no se revisaron (se alcanzo un limite). Mostrando lo que se encontro.",
)

# Provisional greeting, pending fluent ES review (voice.md).
GREETING = Bilingual(
    en="Good afternoon, neighbor.",
    es="Buenas tardes, vecindad.",
)

# The card action label (also on the ChangedItem, kept here for the string audit).
START_COMMENT = Bilingual(
    en="Start a comment",
    es="Comenzar un comentario",
)


# All watcher-produced user-facing strings, for the bilingual-coverage audit test.
ALL_STRINGS: tuple[Bilingual, ...] = (
    PRIVACY, QUIET_WEEK, DEGRADED, PARTIAL, GREETING, START_COMMENT,
)
