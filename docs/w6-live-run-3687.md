# W6 live end-to-end run — meeting 3687

**Agenda:** Planning Commission, Wednesday August 26, 2026
**Source:** https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687
**Model:** amazon.nova-lite-v1:0 (Nova Lite), temp ~0, direct Converse
**Shape:** one controlled fetch, in-memory extraction, live rewrite stage (W6 = 1(b))

This run proves extract → rewrite → verify → persist works on real unseen text. It
does NOT prove ingestion feeds that chain, because ingestion does not persist
document text and extraction was never wired in (the root-cause task).

**Coverage:** English 3/4 verified, Spanish 1/4 verified.
**Actual cost (summed pre-rounding):** $0.000656 for the agenda.
**Rejections:** 4 total — 1 EN (item 2, twice), 3 ES (items 3 and 4 twice each; item
2 ES never attempted because EN never verified).

---

## Item 1 — Approval of the Minutes

**Receipt:** Planning Commission | 2026-08-26 | Item 1 | pp. 2-2 | [source](https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687)
**en_verified:** True (attempt 1) | **es_verified:** True (attempt 1)

**English (verified):**
> The group will review and decide whether to accept the notes from the meeting held on June 24, 2026. The suggestion is to approve the notes as they are. The notes are available for everyone to look at.

**Spanish (verified):**
> El grupo revisara y decidira si aceptan las notas de la reunion celebrada el 24 de junio de 2026. La sugerencia es aprobar las notas tal como estan. Las notas estan disponibles para que todos las revisen.

---

## Item 2 — Prohousing Designation, Citywide

**Receipt:** Planning Commission | 2026-08-26 | Item 2 | pp. 2-3 | [source](https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687)
**en_verified:** False (2 attempts) | **es_verified:** False (0 attempts — ES not attempted because EN never verified)

**Shown (EN fallback — original staff text):**
> 2. Prohousing Designation, Citywide
> The City is applying for a Prohousing Designation to the State of California Department of Housing and Community Development. This designation recognizes jurisdictions that are committed to accelerating housing production, removing barriers to development, and implementing housing-friendly policies. Staff is presenting the draft application for comments and review.
> Recommendation: To approve the draft Prohousing Designation application and formal resolution.
> Staff:  Andrea Palmer, Senior Management Analyst; Rachel Wess, Management Analyst
> Applicant:  City of Ventura
> Materials: staff report, application, resolution, public comment

**[EN NOTE]** A verified plain-English summary could not be produced for this item; showing the original text as published by the city.
**[ES ABSENT]** A verified Spanish version was not produced for this item. No se pudo producir una version verificada en espanol para este punto.

**Why it was rejected — every attempt, the check that fired, its reason, and the rejected text:**

- **EN attempt 1 — REJECTED by `reading_level`:** `reading score 18.9 below floor 33.8 (en)`
  > The City of Ventura is seeking a Prohousing Designation from the State of California Department of Housing and Community Development. This designation is for areas that are dedicated to speeding up housing production, eliminating obstacles to development, and adopting policies that support housing. The draft application is being presented for feedback and review. The City is considering approving this draft application and the formal resolution. The staff members involved are Andrea Palmer, Senior Management Analyst, and Rachel Wess, Management Analyst. The City of Ventura is the applicant. Materials available include the staff report, the application, the resolution, and public comments.

- **EN attempt 2 — REJECTED by `reading_level`:** `reading score 12.8 below floor 33.8 (en)`
  > The City of Ventura is seeking a Prohousing Designation from the State of California Department of Housing and Community Development. This recognition is for areas that are dedicated to increasing housing availability, easing development restrictions, and adopting policies that support housing. The draft application for this designation is being presented for feedback and review. The City Council is considering approving this draft application and the accompanying formal resolution. The staff members involved in this process are Andrea Palmer, Senior Management Analyst, and Rachel Wess, Management Analyst. The materials available for review include a staff report, the application, a resolution, and any public comments.

---

## Item 3 — PROJ-25-0914 Loretta Court Apartments (APN 073-0-058-030)

**Receipt:** Planning Commission | 2026-08-26 | Item 3 | pp. 2-3 | [source](https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687)
**en_verified:** True (attempt 1) | **es_verified:** False (2 attempts)

**English (verified):**
> The city is considering a request for a Major Design Review for a new 19-unit multi-family residential apartment development at Loretta Court Apartments, located at APN: 073-0-058-030. This development will be on a 12,540-square foot site in the Urban General 1 (T4.1 Main St. Frontage) Zone within the Downtown Specific Plan. The project includes 3 warrants (Lot width, Tuck-Under Parking, & 60% 3rd story) and 1 exception (Parking Setback). The California Environmental Quality Act has identified this as an infill project under 15332. The recommendation is to approve the project with certain conditions. The planner for this review is Grant White, Acting Senior Planner, and the applicant is Linda Blackbern of RRM Design Group on behalf of Merewether Trust. The materials being reviewed include a staff report, a vicinity map, a resolution, development standards, plans, and public comments.

**[ES ABSENT]** A verified Spanish version was not produced for this item. No se pudo producir una version verificada en espanol para este punto.

**Why ES was rejected — every attempt, the check(s) that fired, reasons, and the rejected text:**

- **ES attempt 1 — REJECTED by `entity_preservation`, `no_new_entities`, `both_languages`:**
  reason (all three): `output entities not found in source: ['calidad ambiental', 'planificador senior interino', 'zona urban general']`
  > La ciudad esta considerando una solicitud para una revision de diseno importante para un nuevo desarrollo de apartamentos residenciales de multiples unidades de 19 unidades en Loretta Court Apartments, ubicado en APN: 073-0-058-030. El proyecto esta en un sitio de 12,540 pies cuadrados en la Zona Urban General 1 (T4.1 Main St. Frontage) dentro del Plan Especifico del Centro, identificado como Numero de Parcela del Asesor 073-0-058-030. El desarrollo incluye 3 garantias (ancho del lote, estacionamiento bajo techo y 60% del tercer piso) y 1 excepcion (espacio de estacionamiento). La Ley de Calidad Ambiental de California categoriza esto como un proyecto de relleno bajo 15332. El Planificador Senior Interino, Grant White, recomienda aprobar el proyecto con ciertas condiciones. La solicitante es Linda Blackbern de RRM Design Group en nombre de Merewether Trust. La revision incluira un informe del personal, un mapa de la vecindad, una resolucion, estandares de desarrollo, planos y comentarios publicos.

- **ES attempt 2 — REJECTED by `entity_preservation`, `no_new_entities`, `reading_level`, `both_languages`:**
  entity reasons (same three phrases): `output entities not found in source: ['calidad ambiental', 'planificador senior interino', 'zona urban general']`; reading: `reading score 63.2 below floor 64.0 (es)`

---

## Item 4 — PROJ-25-0933 1193 Colina Vista Addition (APN 065-0-224-095)

**Receipt:** Planning Commission | 2026-08-26 | Item 4 | pp. 3-3 | [source](https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_08262026-3687)
**en_verified:** True (attempt 1) | **es_verified:** False (2 attempts)

**English (verified):**
> The city is considering a request to allow a taller building on a hillside property at 1193 Colina Vista. The request is for a major variance to increase the height of the building for a renovation project. This project includes adding a 1,903-square-foot second story to an existing single-story house and doing interior renovations to the first floor. The property is on a 0.28-acre lot in the R-1-10 (Single-Family Residential) zone with a land use designation of Neighborhood Very Low 2, and it is identified as Assessor's Parcel Number 065-0-224-095.
> The city is also considering a recommendation to continue the review of this request until October 28, 2026. The planner for this request is Adams Bernhardt, a Senior Planner, and the applicant is James McGarry from James McGarry Architecture. The city will review a continuance memo and any public comments before making a decision.

**[ES ABSENT]** A verified Spanish version was not produced for this item. No se pudo producir una version verificada en espanol para este punto.

**Why ES was rejected — every attempt, the check(s) that fired, reasons, and the rejected text:**

- **ES attempt 1 — REJECTED by `entity_preservation`, `no_new_entities`, `reading_level`, `both_languages`:**
  entity reason (all): `output entities not found in source: ['calidad ambiental', 'instalaciones existentes', 'planificador senior', 'residencial unifamiliar', 'vecindario muy bajo']`; reading: `reading score 60.0 below floor 64.0 (es)`
  > La ciudad esta considerando una solicitud para permitir un cambio en la altura del edificio para un proyecto de renovacion en 1193 Colina Vista. Este proyecto incluye agregar un segundo piso de 1,903 pies cuadrados a una casa de un solo piso existente y realizar renovaciones interiores en el primer piso. La propiedad esta en un lote de 0.28 acres en la zona R-1-10 (Residencial Unifamiliar), con una designacion de uso del suelo de Vecindario Muy Bajo 2, y esta identificada como Parcela del Asesor Numero 065-0-224-095.
  > La ciudad tambien esta considerando continuar la revision de este proyecto bajo la Ley de Calidad Ambiental de California, especificamente Clase 1 (Instalaciones Existentes), hasta el 28 de octubre de 2026. El planificador para este proyecto es Adams Bernhardt, un Planificador Senior, y el solicitante es James McGarry de James McGarry Architecture. La ciudad revisara un memorando de continuacion y cualquier comentario publico antes de tomar una decision.

- **ES attempt 2 — REJECTED by `entity_preservation`, `no_new_entities`, `reading_level`, `both_languages`:**
  entity reason (same five phrases); reading: `reading score 61.0 below floor 64.0 (es)`

---

## Diagnosis (diagnose, do not fix)

**The three ES failures REFUTE the hyphenated-identifier hypothesis.** The reason
strings name the exact failing entities, and NONE of them are hyphenated
identifiers. The APNs (`073-0-058-030`, `065-0-224-095`), the zone code `T4.1`, the
project codes, and the CEQA section `15332` all PRESERVED correctly — they appear
unchanged in the rejected Spanish and did not trip any check. This is NOT the
`2022-053` / `FA19-1149` class.

The failing entities are all **English descriptive phrases the model translated
into Spanish**, which the extractor then captured as proper-name (raw-compare)
entities absent from the English source:

| Rejected ES entity | English phrase in source |
| --- | --- |
| `calidad ambiental` | (California Environmental Quality Act) |
| `planificador senior interino` | Acting Senior Planner |
| `planificador senior` | Senior Planner |
| `zona urban general` | Urban General (zone) |
| `instalaciones existentes` | Existing Facilities |
| `residencial unifamiliar` | Single-Family Residential |
| `vecindario muy bajo` | Neighborhood Very Low |

This is the SAME class as the task-9 role/body-name gap (`Concejo Municipal`,
`Centro Urbano`, `Distrito Escolar Unificado`) — common-noun descriptive phrases
that translate freely and are not the proper names the raw-compare rule targets.
The task-9 fix added the specific Spanish terms observed THEN; this run surfaces a
new batch of the same class on a different body's vocabulary (planning/zoning
descriptors instead of council/clerk roles).

**Proposed fix (do not apply):** the durable fix is not to keep appending observed
Spanish strings to `_ROLE_OR_BODY` one run at a time — that list will never
converge across every city body's vocabulary. Two candidates, to decide:
  1. **Extend the raw-compare exclusion to descriptive common-noun phrases
     generally**, not just role/body names — e.g. treat a multi-word capitalized
     phrase as raw-compare ONLY when it is a proper name (street, place, person,
     company, identifier), and treat generic descriptive phrases (zone
     descriptions, act names, use designations) as translatable. This is the
     principled version of decision 1, applied to the whole descriptive class.
  2. **Do not extract translated common-noun phrases as entities at all** — tighten
     the proper-noun extractor so a phrase that is a translation of source words
     (not a name copied verbatim) is not treated as a raw-compare entity. Harder to
     do without a name lexicon; risks under-catching a genuinely changed name.
  Recommendation: (1) — it is the same decision-1 principle widened from "role/body"
  to "descriptive common noun," and it is testable against these exact reason
  strings. But it is a real change to the raw-compare rule and needs its own
  calibration pass (must still reject a translated STREET name — the golden-002/es
  adversarial), so it is proposed, not applied.

**Item 2's EN double failure is a different animal:** `reading_level`, scores 18.9
then 12.8, both far below the 33.8 EN floor. NOT an entity problem — the model's
rewrites are long, multi-clause, list-heavy prose ("recognizes jurisdictions that
are committed to accelerating housing production, removing barriers to development,
and implementing housing-friendly policies..."). Flesch Reading Ease scores that
kind of long-sentence, abstract-noun prose as HARD regardless of accuracy. The
source item is itself abstract policy language, so the model faithfully produced
abstract prose and the reading floor correctly caught that it is not plain enough.
The never-fail-open fallback did the right thing: original staff text shown, no
fabrication. Whether the fix is a better prompt (shorter sentences) or accepting
that some policy items just show original text is a separate decision.
