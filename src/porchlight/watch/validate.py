"""Watch-input validation — pure, shared shape for client and server (R3.5, R4.3).

No I/O, no model. The SERVER half of "validate both sides" (security.md: never
trust the front end); the JS client mirrors these same caps in Spec 6. Incoming
shared-link terms take this exact path before they can be applied (R4.3).

Caps, each a value AND a one-line rationale (style.md — guessed is fine, unlabeled
is not; PoC judgment calls, Requirement 3.5):
  - MAX_TERMS = 10:  covers a real neighbor's set of concerns without handing the
                     model a huge prompt to sweep on every live request.
  - MAX_TERM_CHARS = 60:  holds a phrase like "short-term rentals near the beach"
                     while blocking a pasted essay.
Character rule: a term must be printable and contain no control characters — an
injected newline/escape is data we refuse at the door, not something we clean and
pass on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_TERMS = 10
MAX_TERM_CHARS = 60


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a raw watchlist.

    `ok` is True only if every term passed. `terms` is the normalized, accepted
    list (trimmed, de-duplicated, order preserved). `rejections` carries
    (raw_term, reason) for each rejected term so the surface can say what and why —
    never a blank refusal.
    """

    ok: bool
    terms: tuple[str, ...] = ()
    rejections: tuple[tuple[str, str], ...] = ()


def _has_control_chars(s: str) -> bool:
    # Any character below space (newlines, tabs, escapes) or the DEL range.
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in s)


def validate_watchlist(raw_terms: list[str]) -> ValidationResult:
    """Validate and normalize a raw watchlist against the caps (R3.5, R4.3).

    Rules, in order:
      - the whole list may carry at most MAX_TERMS terms (after dropping blanks);
      - each term, trimmed, must be non-empty, at most MAX_TERM_CHARS, printable,
        and free of control characters;
      - duplicate terms (case-insensitive, after trim) collapse to the first.

    Never raises: malformed input yields a structured rejection, not a crash. The
    watchlist is untrusted data (never.md #9) — this function only accepts or
    rejects it, it never executes anything in it.
    """
    if not isinstance(raw_terms, list):
        return ValidationResult(ok=False, rejections=(("<input>", "watchlist must be a list of terms"),))

    accepted: list[str] = []
    rejections: list[tuple[str, str]] = []
    seen: set[str] = set()

    # List-level cap first: too many terms is a rejection of the list, and we do not
    # silently truncate (a dropped term the user meant to watch is a missed match).
    non_blank = [t for t in raw_terms if isinstance(t, str) and t.strip()]
    if len(non_blank) > MAX_TERMS:
        return ValidationResult(
            ok=False,
            rejections=((f"<{len(non_blank)} terms>", f"too many terms: {len(non_blank)} > {MAX_TERMS}"),),
        )

    for raw in raw_terms:
        if not isinstance(raw, str):
            rejections.append((str(raw), "term must be text"))
            continue
        term = raw.strip()
        if not term:
            continue  # blanks are dropped, not rejected
        if len(term) > MAX_TERM_CHARS:
            rejections.append((raw, f"term too long: {len(term)} > {MAX_TERM_CHARS} chars"))
            continue
        if _has_control_chars(term):
            rejections.append((raw, "term contains control characters"))
            continue
        if not term.isprintable():
            rejections.append((raw, "term contains non-printable characters"))
            continue
        key = term.casefold()
        if key in seen:
            continue  # duplicate collapses to the first occurrence
        seen.add(key)
        accepted.append(term)

    return ValidationResult(ok=not rejections, terms=tuple(accepted), rejections=tuple(rejections))
