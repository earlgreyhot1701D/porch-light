"""Body registry for the verifier — the closed set of known Ventura bodies and
their accepted name renderings (W6 finding 1, decision: body comes off the record).

Sourced from the adapter registry (`adapters.ventura.registry.BODIES`) — bodies are
never invented here. This adds, per body, the accepted SPANISH rendering(s)
alongside the city's English name, so check 4 can confirm a rewrite names the
record's OWN body (in either language) and reject a rewrite that names a DIFFERENT
body — language-independently.

Design principle (decisions doc): never verify by inference what the record already
states. The body is a deterministic field on the record; check 4 checks the
rewrite for CONTRADICTION of it, it does not re-derive the body as an entity. That
is what made the entity-matching route brittle (greedy spans; see KNOWN-LIMITATIONS).

Spanish renderings are a small closed set of REAL observed/accepted translations,
not a vocabulary. Add one only when a rewrite legitimately uses it for that body.
"""

from __future__ import annotations

import re
import unicodedata

from porchlight.adapters.ventura.registry import BODIES

# Accepted Spanish rendering(s) per body_id. Only bodies whose Spanish name we have
# actually seen/accepted are listed; others are recognized by their English name
# alone until a real Spanish rendering is observed (closed set, never guessed).
_ES_RENDERINGS: dict[str, tuple[str, ...]] = {
    "city_council": ("Concejo Municipal", "Concejo", "Ayuntamiento"),
    "planning_commission": ("Comision de Planificacion", "Comision de Planeacion"),
    "design_review_committee": ("Comite de Revision de Diseno",),
    "water_commission": ("Comision de Agua",),
}


def _fold(s: str) -> str:
    """Match key: casefold, collapse whitespace, strip accents. Display keeps accents."""
    collapsed = re.sub(r"\s+", " ", (s or "").strip()).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", collapsed) if not unicodedata.combining(c))


# body_id -> set of folded accepted names (EN + ES renderings).
_ACCEPTED_BY_ID: dict[str, set[str]] = {}
# folded name -> body_id, for detecting which body a rewrite names.
_ID_BY_NAME: dict[str, str] = {}

for _b in BODIES:
    names = {_b.name_en, *_ES_RENDERINGS.get(_b.body_id, ())}
    folded = {_fold(n) for n in names}
    _ACCEPTED_BY_ID[_b.body_id] = folded
    for f in folded:
        _ID_BY_NAME[f] = _b.body_id


def accepted_names(body_id: str) -> set[str]:
    """Folded accepted name forms (EN + ES) for a body_id. Empty if unknown."""
    return _ACCEPTED_BY_ID.get(body_id, set())


def find_named_bodies(text: str) -> set[str]:
    """Return the body_ids whose registered name (EN or accepted ES) appears in text.

    Substring match on folded text, so a body named inside prose ("The Planning
    Commission will...") is detected. Only KNOWN bodies match — a generic phrase
    that is not a registered body name returns nothing (absence is handled by the
    caller, not treated as a body).
    """
    folded_text = _fold(text)
    found: set[str] = set()
    for name, body_id in _ID_BY_NAME.items():
        # Word-ish boundary: the folded name surrounded by non-alphanumerics or ends.
        if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", folded_text):
            found.add(body_id)
    return found
