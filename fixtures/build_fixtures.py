"""Build the view fixtures (R6, §25): sample.json and the hostile ugly.json.

Run: `uv run python fixtures/build_fixtures.py`

Contract-first (§25): these files are shaped to `web/contract.py` so the mock's
render path swaps from an inline array to a fixture to a live endpoint without
reshaping. The mock reads `fixtures/sample.json`; `fixtures/ugly.json` is the
hostile case the layout must survive (long Ventura body names, long item text,
the 95th-percentile packet length) — the classic place a mock layout breaks
(§25b "Riverdale -> Ventura is not find-and-replace").

Honesty rules baked in:
  - Everything here is `synthetic: true` until real extraction fills it (§25). The
    sample-data notice stays until the data is real.
  - Absence uses the exact voice.md form "not located at [url] as of [timestamp]".
  - The reserved deadline amber is gated by `deadline_actionable`, set here only on
    the one approaching, still-actionable deadline.

This is a build script (a fixture GENERATOR), not test data hand-authored to a
desired output — it seeds INPUTS shaped to the contract (testing.md #4). The
golden set, by contrast, is the human ground-truth artifact and is not built here.
"""

from __future__ import annotations

import json
from pathlib import Path

from porchlight.web.contract import (
    Bilingual,
    ChangedItem,
    Heartbeat,
    Mark,
    Receipt,
    SourceStatus,
    Tone,
    View,
)

_FIXTURES_DIR = Path(__file__).parent

# The 95th-percentile packet page count, to be REPLACED with the real computed
# value once ingestion has a corpus (§25). Marked synthetic until then.
_P95_PACKET_PAGES_SYNTHETIC = 312


def _heartbeat() -> Heartbeat:
    return Heartbeat(
        city_read=Bilingual("City read 10:42 AM", "Ciudad revisada 10:42 AM"),
        read_count=Bilingual("20 of 21 bodies read", "20 de 21 organismos leidos"),
        next_check=Bilingual(
            "Next check: Tuesday, 8:00 AM · Pacific, city local time",
            "Proxima revision: martes, 8:00 AM · Pacifico, hora local de la ciudad",
        ),
    )


def _recent_checks() -> tuple[SourceStatus, ...]:
    # One unreachable body, phrased as honest absence — never "overdue/failed".
    unreachable = SourceStatus(
        datetime="2026-08-16T10:42:00-07:00",
        date=Bilingual("Fri, Aug 16", "Vie, 16 ago"),
        time="10:42 AM · Pacific, city local time",
        body=Bilingual(
            "Planning Commission could not be read",
            "No se pudo leer la Comision de Planificacion",
        ),
        evidence=Bilingual(
            "not located at cityofventura.ca.gov/planning as of Aug 16, 10:42 AM PT",
            "no se localizo en cityofventura.ca.gov/planning al 16 de agosto, 10:42 AM PT",
        ),
    )
    return (unreachable,)


def _sample_view() -> View:
    """A 'changed' view: two matches, one with an approaching actionable deadline."""
    hot = ChangedItem(
        id="supplemental-packet",
        tone=Tone.HOT,
        mark=Mark.ADDED,
        status=Bilingual("New material added", "Material nuevo agregado"),
        official_term=Bilingual(
            "Official term: Supplemental packet",
            "Termino oficial: paquete suplementario",
        ),
        heading=Bilingual(
            "Extra documents were added about the wine bar proposed at 123 Elm Street, "
            "including parking and noise conditions.",
            "Se agregaron documentos adicionales sobre el bar de vinos propuesto en 123 Elm Street, "
            "incluidas las condiciones de estacionamiento y ruido.",
        ),
        match_reason=Bilingual(
            "Matched your watch: \"Can they put a bar next to my house?\"",
            "Coincidio con su alerta: \"Pueden poner un bar junto a mi casa?\"",
        ),
        scale_note=Bilingual(
            f"This packet is {_P95_PACKET_PAGES_SYNTHETIC} pages. The item shown here is 13 pages.",
            f"Este paquete tiene {_P95_PACKET_PAGES_SYNTHETIC} paginas. El elemento aqui es de 13 paginas.",
        ),
        receipt=Receipt(
            line=Bilingual(
                "Planning Commission · Aug 25, 2026 · Item 7 · pp. 118-130",
                "Comision de Planificacion · 25 ago 2026 · Punto 7 · pp. 118-130",
            ),
            source_href="https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08252026-3685#page=118",
            source_label=Bilingual("Open the source document", "Abrir el documento original"),
        ),
        deadline=Bilingual(
            "Comment closes tomorrow at 5:00 PM · Pacific, city local time",
            "El comentario cierra manana a las 5:00 PM · Pacifico, hora local de la ciudad",
        ),
        deadline_actionable=True,  # the ONE place the reserved amber applies
        action=Bilingual("Start a comment", "Comenzar un comentario"),
    )
    calm = ChangedItem(
        id="cancelled-meeting",
        tone=Tone.CALM,
        mark=Mark.OFF,
        status=Bilingual("Meeting cancelled", "Reunion cancelada"),
        official_term=Bilingual("Official term: Cancellation", "Termino oficial: cancelacion"),
        heading=Bilingual(
            "The Historic Preservation Committee meeting you were watching was cancelled.",
            "La reunion del Comite de Preservacion Historica que seguia fue cancelada.",
        ),
        match_reason=Bilingual(
            "Matched your watch: \"Street trees on Juniper Avenue\"",
            "Coincidio con su alerta: \"Arboles en Juniper Avenue\"",
        ),
        scale_note=Bilingual("", ""),
        receipt=Receipt(
            line=Bilingual(
                "Historic Preservation Committee · Aug 20, 2026 · notice",
                "Comite de Preservacion Historica · 20 ago 2026 · aviso",
            ),
            source_href="https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08202026-3670",
            source_label=Bilingual("Open the source document", "Abrir el documento original"),
        ),
        deadline=None,  # no actionable deadline -> no amber, by data
        deadline_actionable=False,
        action=None,
    )
    return View(
        is_quiet=False,
        heartbeat=_heartbeat(),
        recent_checks=_recent_checks(),
        changed=(hot, calm),
        synthetic=True,
    )


def _ugly_view() -> View:
    """The hostile case (§25): long real Ventura body names + long item text.

    Ventura's longest body names ("Measure O Citizens Oversight Committee") and
    real item text run far longer than hand-tuned sample copy. If the layout holds
    on this, it holds. Still synthetic until built from a real oversized agenda.
    """
    long_body_en = "Measure O Citizens Oversight Committee — Infrastructure and Capital Projects Subcommittee"
    long_body_es = "Comite de Supervision Ciudadana de la Medida O — Subcomite de Infraestructura y Proyectos de Capital"
    long_heading_en = (
        "The committee will consider a resolution authorizing the City Manager to execute a "
        "professional services agreement, and amendments thereto, for the comprehensive "
        "rehabilitation of the Cabrillo Boulevard corridor between Seaward Avenue and Harbor "
        "Boulevard, including but not limited to pavement reconstruction, storm drain "
        "improvements, undergrounding of utilities, and the installation of protected bicycle "
        "facilities, in an amount not to exceed $4,750,000."
    )
    long_heading_es = (
        "El comite considerara una resolucion que autoriza al Administrador de la Ciudad a "
        "ejecutar un acuerdo de servicios profesionales, y sus enmiendas, para la rehabilitacion "
        "integral del corredor de Cabrillo Boulevard entre Seaward Avenue y Harbor Boulevard, "
        "incluida la reconstruccion del pavimento, mejoras del drenaje pluvial, el soterramiento "
        "de servicios publicos y la instalacion de ciclovias protegidas, por un monto que no "
        "exceda los $4,750,000."
    )
    item = ChangedItem(
        id="long-item",
        tone=Tone.HOT,
        mark=Mark.ADDED,
        status=Bilingual("New material added", "Material nuevo agregado"),
        official_term=Bilingual(
            "Official term: Supplemental packet", "Termino oficial: paquete suplementario"
        ),
        heading=Bilingual(long_heading_en, long_heading_es),
        match_reason=Bilingual(
            "Matched your watch: \"bike lanes and street reconstruction downtown\"",
            "Coincidio con su alerta: \"ciclovias y reconstruccion de calles en el centro\"",
        ),
        scale_note=Bilingual(
            "This packet is 512 pages. The item shown here is 41 pages.",
            "Este paquete tiene 512 paginas. El elemento aqui es de 41 paginas.",
        ),
        receipt=Receipt(
            line=Bilingual(
                f"{long_body_en} · Sep 2, 2026 · Item 12 · pp. 214-255",
                f"{long_body_es} · 2 sep 2026 · Punto 12 · pp. 214-255",
            ),
            source_href="https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_09022026-3700#page=214",
            source_label=Bilingual("Open the source document", "Abrir el documento original"),
        ),
        deadline=Bilingual(
            "Comment closes in 3 days, at 5:00 PM · Pacific, city local time",
            "El comentario cierra en 3 dias, a las 5:00 PM · Pacifico, hora local de la ciudad",
        ),
        deadline_actionable=True,
        action=Bilingual("Start a comment", "Comenzar un comentario"),
    )
    return View(
        is_quiet=False,
        heartbeat=_heartbeat(),
        recent_checks=_recent_checks(),
        changed=(item,),
        synthetic=True,
    )


def build() -> None:
    """Write both fixtures to disk, pretty-printed, UTF-8."""
    (_FIXTURES_DIR / "sample.json").write_text(
        json.dumps(_sample_view().as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (_FIXTURES_DIR / "ugly.json").write_text(
        json.dumps(_ugly_view().as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    build()
    print(f"Wrote sample.json and ugly.json to {_FIXTURES_DIR}")
