"""Build fixtures/sample.json from the stored 3685/3687 items (Spec 6, §25).

Reads the verified rewrites the condition-5 join persisted and shapes them to the
view contract (web/contract.py View/ChangedItem). The static site renders from this
JSON; the render path does not care whether the JSON came from here or a live
endpoint later (§25 — wiring is a path swap).

Every shown item is the VERIFIED rewrite, or the honest EN-fallback text with its
note (never.md #7). Receipts are copied from the record (never.md #6). Deadlines are
copied from source or None (never.md #1) — none of these items carry a comment
deadline in the stored record, so `deadline` is null and no amber lights (voice.md).

Run: AURORA_* env set, `uv run python -m porchlight.web.build_fixture`.
Writes fixtures/sample.json (relative to repo root).
"""

from __future__ import annotations

import json
import os

# Meeting metadata (from the meetings/bodies rows; stable, copied from the record).
MEETINGS = {
    "doc_sha256_5cde9f5a484b22df96d45cceb25dc22bdb92ec6fee623e20662ce8b81b79f909": {
        "meeting_id": "3685",
        "body_en": "City Council", "body_es": "Concejo Municipal",
        "meeting_date_en": "Aug 25, 2026", "meeting_date_es": "25 ago 2026",
        "url": "https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08252026-3685",
    },
    "doc_sha256_d17d08a52bab0e87f2b2f4ce5ea5c222785a1c30cab77a4afbf81226b4dfe457": {
        "meeting_id": "3687",
        "body_en": "Planning Commission", "body_es": "Comision de Planificacion",
        "meeting_date_en": "Aug 26, 2026", "meeting_date_es": "26 ago 2026",
        "url": "https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687",
    },
}

_FALLBACK_STATUS = {
    "en": "Shown as published by the city",
    "es": "Mostrado tal como lo publico la ciudad",
}


def _pages(ps: int, pe: int) -> str:
    return f"p. {ps}" if ps == pe else f"pp. {ps}-{pe}"


def _receipt_line(m: dict, num: str, ps: int, pe: int, lang: str) -> str:
    body = m["body_en"] if lang == "en" else m["body_es"]
    date = m["meeting_date_en"] if lang == "en" else m["meeting_date_es"]
    item = f"Item {num}" if lang == "en" else f"Punto {num}"
    return f"{body} · {date} · {item} · {_pages(ps, pe)}"


def _source_href(m: dict, ps: int) -> str:
    sep = "&" if "?" in m["url"] else "#"
    return f"{m['url']}{sep}page={ps}"


def build_view(rows: list[dict]) -> dict:
    """Shape stored item rows into the View contract dict the site renders."""
    changed = []
    for r in rows:
        m = MEETINGS[r["doc"]]
        num = str(r["num"]).rstrip(".")
        ps, pe = int(r["ps"]), int(r["pe"])
        en_verified = bool(r["env"])
        es_verified = bool(r["esv"])

        # Shown summary: verified EN, or the honest EN fallback text (never.md #7).
        heading_en = r["en"]
        # ES: verified ES, or the honest ES-absent note (never fabricated).
        summary_es = r["es"] if es_verified and r["es"] else r["es_absent"]

        status_en = "New material added" if en_verified else _FALLBACK_STATUS["en"]
        status_es = "Material nuevo agregado" if en_verified else _FALLBACK_STATUS["es"]

        changed.append({
            "id": f"{m['meeting_id']}-{num}",
            "tone": "calm",  # none of these carry an actionable deadline -> never hot
            "mark": "added",
            "status": {"en": status_en, "es": status_es},
            "official_term": {
                "en": f"{m['body_en']} agenda item {num}",
                "es": f"{m['body_es']}, punto {num}",
            },
            "heading": {"en": heading_en, "es": summary_es},
            "match_reason": {
                # No live watchlist on the static page: the "why" line explains the
                # item is shown as a real stored record, never a fabricated match.
                "en": "Shown from the city's real agenda record.",
                "es": "Mostrado desde el registro real de la agenda de la ciudad.",
            },
            "scale_note": {
                "en": f"This item is on {_pages(ps, pe)} of the agenda.",
                "es": f"Este punto esta en {_pages(ps, pe)} de la agenda.",
            },
            "receipt": {
                "line": {
                    "en": _receipt_line(m, num, ps, pe, "en"),
                    "es": _receipt_line(m, num, ps, pe, "es"),
                },
                "source_href": _source_href(m, ps),
                "source_label": {
                    "en": f"open the agenda at page {ps}",
                    "es": f"abrir la agenda en la pagina {ps}",
                },
            },
            "deadline": None,        # copied from source or None (never.md #1)
            "deadline_actionable": False,
            "fallback_note": (
                {"en": r["note_en"], "es": r["es_absent"]}
                if (r["note_en"] or not es_verified) else None
            ),
            "en_verified": en_verified,
            "es_verified": es_verified,
        })

    return {
        "is_quiet": False,  # we have real changed items to show
        "synthetic": False,  # this is REAL city data (not synthetic) — notice can go
        "heartbeat": {
            "city_read": {"en": "City read from stored agendas", "es": "Ciudad leida de agendas almacenadas"},
            "read_count": {"en": "2 meetings read", "es": "2 reuniones leidas"},
            "next_check": {"en": "Hourly, on schedule", "es": "Cada hora, segun lo programado"},
        },
        "recent_checks": [],
        "changed": changed,
    }


def _load_rows() -> list[dict]:
    from db import data_api

    be = data_api.get_backend()
    rows = be.query(
        "SELECT i.document_id doc, i.item_number num, i.page_start ps, i.page_end pe, "
        "ir.en_verified env, ir.es_verified esv, ir.en_text en, ir.es_text es, "
        "ir.note_en note_en, ir.es_absent_note es_absent "
        "FROM item_rewrites ir JOIN items i ON i.item_id = ir.item_id "
        "WHERE i.document_id IN (%s, %s) "
        "ORDER BY i.document_id, length(i.item_number), i.item_number",
        list(MEETINGS.keys()),
    ).rows
    return rows


def main() -> None:
    rows = _load_rows()
    view = build_view(rows)
    out_path = os.path.join(os.getcwd(), "web", "sample.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(view, f, ensure_ascii=False, indent=2)
    print(f"wrote {out_path} ({len(view['changed'])} items)")


if __name__ == "__main__":
    main()
