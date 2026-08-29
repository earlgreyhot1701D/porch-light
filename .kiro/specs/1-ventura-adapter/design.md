# Design Document — Spec 1: Ventura Adapter

## Scope

Deterministic adapter: bodies → meetings → documents, with role classification,
ingestion horizon, and surfacing rule. No packet-content extraction, no model,
no scheduler (Spec 2/3 own those). References decisions §34 (platform/compliance)
and §35 (server-rendered enumeration finding). Compliance and rigor budget are
settled in requirements.md and not restated here.

## Vocabulary correction (§35a) — "packet" is the wrong word for Ventura

Ventura publishes 2-to-14-page **agendas**, not multi-hundred-page packets
(verified: 5 sampled agendas, 2–14 pages, 150–940 KB). "Packet" is inaccurate for
this city, and misdescribing what a public body produced is a never.md concern
(#1, do not misdescribe source material), not a style preference. A Ventura
resident would notice, and noticing is the failure this product cannot afford.

**Rules applied in this spec and forward:**

- User-facing and spec language uses **"agenda"** or **"the document"**, matching
  what the city calls it. This design uses those words throughout.
- Internal code nouns use `document` where we are free to choose (new code in
  `adapters/`). We do **not** refactor working code for vocabulary.
- **Deliberate exceptions that STAY unchanged:**
  - The redaction key patterns in `src/porchlight/log.py` (`packet_text`,
    `source_text`, `document_content`, `page_content`) remain. They are defensive
    substring matches; narrowing them weakens a security control (§security).
  - `design/porch-light-ui-v1.html` is **not touched here.** It is the accepted
    mock under ui-contract.md; the copy sweep ("packet" in the hero panel, the
    §11.5 "read 3 packets, 412 pages" demo line, voice.md) happens at **Spec 6**
    when the UI is wired. Recorded in the Spec 6 backlog with §35a as the reason.

## Module layout (per structure.md: one file, one responsibility)

All under `adapters/` (deterministic, pure where possible):

```
adapters/
  ventura/
    registry.py       # R1: static body registry + hand-verified date. Data + loader.
    enumerate.py      # R2: parse server-rendered AgendaCenter HTML → meeting list.
    previous_versions.py  # R2.3: follow PreviousVersions → version/supplemental trail.
    classify.py       # R3: pure document-role classifier. No I/O, no model.
    horizon.py        # R4 + R5: ingestion horizon + surfacing rule. Pure functions.
    fetch.py          # R7: good-citizen HTTP (allowlist, conditional GET, backoff, 1 concurrent).
    models.py         # dataclasses: Body, Meeting, Document. No behavior.
    hash.py           # R3.7: content-hash document_id.
```

`fetch.py` is the only module that touches the network. `classify.py`,
`horizon.py`, `hash.py`, `models.py` are pure and are where the property tests
live (the two invisible-failure surfaces: parser and horizon/surfacing).

## Data flow

```
registry (bodies)
   │  for each body, fetch its AgendaCenter HTML (fetch.py)
   ▼
enumerate.py ── parses served HTML ──▶ [Meeting stubs: body_id, date, type, current Agenda/Minutes URLs]
   │  for each meeting IN HORIZON only (horizon.py gate), fetch PreviousVersions (fetch.py)
   ▼
previous_versions.py ── parses PV HTML ──▶ [full document set per meeting: ArchivedAgenda*, ArchivedMinutes*, supplemental/attachment entries]
   │
   ▼
classify.py ── pure ──▶ each document tagged: agenda | amended_agenda | supplemental | cancellation | spanish_edition | minutes | unclassified
   │
   ▼
horizon.py surfacing rule ──▶ each meeting flagged upcoming | past (city-local date)
   │
   ▼
hand off structured records to storage (Spec 2 owns the schema)
```

Key ordering decision: **the horizon gate runs before the PreviousVersions and
PDF fetches**, so out-of-window meetings cost one line in the already-fetched
index parse and zero additional fetches. Enumeration still walks the full index
(one fetch per body page), but per-meeting fetching is horizon-gated.

## Enumeration mechanism (resolves R2.1, was deferred from requirements)

The AgendaCenter HTML is server-rendered and contains, per meeting, a
`/AgendaCenter/PreviousVersions/_<MMDDYYYY>-<id>` link plus current
`ViewFile/Agenda` and `ViewFile/Minutes` links. The `_<MMDDYYYY>` segment gives
the meeting date deterministically; the `<id>` is the meeting's stable id.

- **Meeting date** comes from the `_MMDDYYYY` URL segment, cross-checked against
  the date printed in the agenda PDF's text layer (R2.4 — source text is
  authoritative; the URL segment is the index key). A mismatch is logged and the
  PDF text wins.
- **Meeting type** (regular / special / adjourned / closed) is read from the
  agenda PDF's first-page text (verified present: "SPECIAL MEETING - 5:00 P.M.",
  "CLOSED SESSION – 4:00 P.M."), not guessed from the URL.
- **Version trail** comes from the PreviousVersions page (R2.3): it lists
  `ArchivedAgenda`/`ArchivedMinutes` versions and any supplemental/attachment
  entries. This is the only place amendments appear; the index shows only current.
- No headless browser. The category-filter widget is JS-rendered and unused.

## Document role classification (R3, pure function)

`classify(document_ref) -> Role` keyed on deterministic signals only:

| Signal | Role inferred |
| --- | --- |
| `ViewFile/Agenda/` current + no later version | `agenda` |
| `ViewFile/ArchivedAgenda/` with a newer Agenda for same meeting | `amended_agenda` |
| PV entry labeled supplemental / attachment | `supplemental` |
| Title/text contains a cancellation marker ("CANCEL", "CANCELLED") | `cancellation` |
| Language markers (title "Español"/"Spanish", `es` edition) | `spanish_edition` |
| `ViewFile/Minutes/` or `ArchivedMinutes/` | `minutes` |
| none match confidently | `unclassified` (R3.6 — never guess) |

- **Amended vs supplemental** distinguished by whether the item replaces the
  agenda (a newer full version → amended) or adds to it (a labeled supplemental
  entry → supplemental). Both associate to the existing meeting id, never a new
  meeting (R3.3).
- **Spanish edition** links to the same meeting id as its English counterpart
  (R3.4), not a separate meeting.
- **Cancellation** marks the meeting cancelled without treating the document as
  new agenda content (R3.2).
- **document_id = content hash** (R3.7): identical re-post → same id → idempotent.
- `classify` performs **no network I/O** so it is trivially property-testable.

## Ingestion horizon and surfacing (R4, R5, pure)

- `in_horizon(meeting_date, today_city_local) -> bool`: True iff
  `today - T2 <= meeting_date <= today + T1` (T2=14d back, T1=30d ahead).
  Enforced **before** any per-meeting fetch (R4.3).
- `is_upcoming(meeting_date, now_city_local) -> bool`: True iff
  `meeting_date >= today_city_local`. Independent of posting/ingestion (R5.1–5.2):
  an agenda amended after a past meeting is ingested (if in horizon) but never
  upcoming.
- Both computed in **America/Los_Angeles**, with an explicit **DST-boundary test**
  (R5.3, R6.4): a meeting at 5:00 PM city-local on a spring-forward and a
  fall-back date must classify correctly regardless of the runner's zone or UTC.

## Run budget arithmetic (against T11 = 10-minute whole-run timeout)

**Measured per-fetch latency** (real, permitted host, single request):
index page ~0.34s, PreviousVersions ~0.70s, agenda PDF 0.29–0.45s. Round up to a
conservative **1.5s per fetch** to absorb backoff, TLS, and variance.

**Constants:** max 1 concurrent (§7). Full index has **129 meetings** (dated
2023-03-15 .. 2026-08-26). The current horizon (2026-08-12 .. 2026-09-25) admits
**10 meetings** (measured against the live index today).

**Fetch count for one run:**

| Phase | Fetches | Note |
| --- | --- | --- |
| Enumeration | ~1 per body page | The index/body pages are walked to read the 129-entry list. Ventura's bodies share the AgendaCenter; budget ≤ ~25 body/category page fetches to be safe. |
| PreviousVersions | 1 per in-horizon meeting = **10** | Horizon-gated (R4.3). Out-of-window meetings cost 0 fetches. |
| Agenda/Minutes PDFs | ≤ ~2 per in-horizon meeting = **~20** | Current agenda + current minutes; conditional GET (R7.3) skips unchanged files, so steady-state is far lower. |
| Supplemental/archived | a few, only if present in PV trail | Bounded by T13 (max 50 docs/body/run). |

**Worst-case first run (no conditional-GET skips):**
`25 (enumeration) + 10 (PV) + 20 (PDFs) + ~10 (archived/supplemental) ≈ 65 fetches`.
At 1.5s serial: **~98 seconds ≈ 1.6 minutes**. Against T11 = 10 minutes, that is
**~6x margin**. Comfortable fit.

**Steady-state run (hourly, conditional GET skips unchanged):** most PDFs return
304 and are not downloaded; fetch count drops to enumeration + PV for the ~10
in-horizon meetings ≈ 35 fetches ≈ **under a minute**.

**Stress note:** even if the horizon were widened to admit all 129 meetings and
every one had a PV fetch plus two PDFs (≈ 400 fetches × 1.5s = 10 minutes), that
would sit right at T11 — which is exactly why the horizon gate exists and runs
before fetching. The design fits with margin **because** the horizon is enforced
first, not after. If a future body proves much larger, the fix is a per-run
meeting cap (extend T13 to a per-run total), not raising T11 above the lock TTL
(T12=15m) — the ordering constraint `T11 < T12 < T14` must hold.

## Cost headroom for Spec 3 (§27 model comparison)

The 2-to-14-page reality (vs. the assumed hundreds) drops per-document model cost
roughly tenfold. Two consequences for Spec 3, recorded here so the decision is
made on this basis:

- §27's Nova-Lite-vs-Claude verifier-rejection comparison can run on a **wide
  sample** of real agendas rather than a token few, so the measured number is
  more trustworthy.
- A **stronger production model is affordable** within the credit budget. Spec 3's
  biggest unknown (can we afford quality) just got smaller.
- **This headroom goes to model quality, not to scope.** No new features are
  justified by the cheaper documents; the scope in §10 stands.

## Error handling and honest states (R6)

- Per-body failure is isolated: one body's fetch/parse failure emits the honest
  empty state for that body and the run continues (R2.5).
- Absence is rendered exactly as `not located at [url] as of [timestamp]` (R6.1),
  never "missing/late/overdue", never carried by color alone.
- Every `try/except` around a fetch or parse writes to the failure log (never a
  silently swallowed exception, §security / never.md #12).
- Degraded dependency → honest empty state, never fabricated (R6.5, never.md #7).

## Testing (rigor budget: working rigor + property tests on invisible surfaces)

**Property tests (Hypothesis) — where a wrong answer is invisible:**
- `classify.py`: generated document refs never crash, never return a role whose
  signal is absent, and unmatched inputs return `unclassified` (never a guess).
- `horizon.py`: `in_horizon` and `is_upcoming` are monotonic in date and correct
  across the DST boundary; a post-meeting amendment is never `upcoming`.

**Working-rigor tests (real fixtures from the live site):**
- The correct meeting list for a known week for City Council and Planning
  Commission, checked by hand (pass gate #1).
- Real examples of each role that exists in Ventura data (agenda, amended,
  supplemental, cancellation, Spanish edition, minutes) classify correctly.
- Stale-agenda tests: out-of-horizon document rejected before fetch; amended-after-
  meeting document ingested but not surfaced (pass gate #2).

**Not property-tested** (verifiable by reading): registry contents, URL
construction, status strings, the fetch posture config.

Fixtures are built from real Ventura documents saved into `tests/fixtures/`
(a small set, including one amended meeting and one cancellation), so tests do
not hit the network on every run. Live checks are marked and run deliberately.

## Explicitly out of scope (unchanged from requirements)

Packet-content extraction, page ranges, any model call, the scheduler/lock/queue,
and the storage schema. Spec 1 hands structured records to the boundary Spec 2 owns.
