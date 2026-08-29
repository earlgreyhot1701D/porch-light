# Implementation Plan: Spec 1 — Ventura Adapter

## Overview

Build the deterministic adapter: body registry → meeting enumeration from the
single combined AgendaCenter index → PreviousVersions version trail → document
role classification → ingestion horizon + surfacing rule, all honoring the
good-citizen fetch posture. No packet-content extraction, no model, no scheduler
(Spec 2/3). Everything references decisions §34 (compliance) and §35 (findings).

Ordering: pure logic first (models, hash, classify, horizon) because it is cheap,
testable, and everything else composes it; then the network layer (fetch); then
enumeration and the version trail that depend on both; then the live pass-gate
verifications and the posting-lead-time measurement.

Rigor budget (style.md): **working rigor** on real Ventura inputs, plus
**property tests only** on the two invisible-failure surfaces — the parser and
the horizon/surfacing rules. No property tests on registry data, URL building, or
status strings.

Tags: [PERMANENT] ships in `adapters/`. [VERIFICATION] confirms an assumption
against the live site. [TEST] is a test deliverable that gates the block.

## Tasks

- [ ] 0. Wave-0 verifications (cheap checks that can change the product; run before any code)
  - [x] 0.1 VERIFICATION: posting lead time (§35e) — MOVED here from 12.1
    - Better than planned: the posted date is IN the combined index HTML per row ("Meeting Aug25, 2026 — Posted Aug19, 2026"), so no separate 20-call measurement was needed. Parsed n=135 meetings.
    - RESULT: **median lead = 5 days, minimum = 0 days** (13 same-day postings, i.e. special/emergency meetings), typical cluster 3–6 days, max 66 (far-advance placeholders). Honest promise: "about 5 days to act, sometimes same-day." The 0-day minimum is the number Spec 5's watch cadence must beat; the earlier "72 hours" assumption was wrong (low).
    - _Requirements: pass gate 5, 9.3_
  - [x] 0.2 VERIFICATION: does the combined index carry body attribution?
    - RESULT: YES. The combined `/AgendaCenter` HTML server-renders 152 `.catAgendaRow` elements (129 with meeting links) grouped under body-name headers. Attribution signal: each meeting row's nearest preceding body header (e.g. "City Council"). All 129 meetings attributed to **21 named bodies** (matches §3's "21 bodies" exactly): City Council 30, Arts & Culture 12, Planning Commission 12, Director's Hearing 11, Design Review 10, Parks & Rec 10, Historic Preservation 8, and 14 more. NOT a stop-and-report — attribution works.
    - _Requirements: 2.1, 2.2_

- [x] 1. Data models and content-hash id [PERMANENT]
  - [x] 1.1 Create `adapters/ventura/models.py` with frozen dataclasses `Body`, `Meeting`, `Document`
    - Done. `DocumentRole` enum (six roles + `unclassified`), `MeetingType` enum, frozen `Body`/`Document`/`Meeting`. Meeting carries `start_time_local` (None when unparseable). No behavior, no I/O. Verified: frozen, constructs cleanly.
    - _Requirements: 2.2, 3.1_
  - [x] 1.2 Create `adapters/ventura/hash.py` — content-hash `document_id`
    - Done. SHA-256, `doc_sha256_<hex>` prefix. Verified: same bytes → same id, different bytes → different id.
    - _Requirements: 3.7_

- [x] 2. Document role classifier [PERMANENT]
  - [x] 2.1 Implement `adapters/ventura/classify.py` — pure `classify(url, title) -> Role`
    - Done. Keyed on REAL verified Ventura strings: "**CANCELLED** ..." → cancellation; Spanish title markers → spanish_edition; "Amended ..." → amended; "Supplemental Packet" → supplemental; ViewFile Minutes/ArchivedMinutes → minutes; Agenda/ArchivedAgenda → agenda; else unclassified. No I/O, no model, never raises.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [x] 2.2 Property test: classifier never guesses, never crashes [TEST]
    - Done. 8 example tests (real strings) + 2 property tests. `# Feature: 1-ventura-adapter, Property 1: classifier soundness`.
    - _Requirements: 3.1, 3.6_

- [x] 3. Ingestion horizon and surfacing rule [PERMANENT]
  - [x] 3.1 Implement `adapters/ventura/horizon.py` — `in_horizon()` and `is_upcoming()`
    - Done. `is_upcoming` compares meeting START datetime (city local), uses parsed time, end-of-day fallback with logged flag. All America/Los_Angeles via tzdata.
    - _Requirements: 4.1, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 3.2 Property test: horizon + surfacing correctness including DST [TEST]
    - Done. 5PM boundary asserted at 4:59/5:01 on BOTH spring-forward (Mar 8 2026) and fall-back (Nov 1 2026); UTC-runner case; monotonic property. `# Feature: 1-ventura-adapter, Property 2`.
    - _Requirements: 4.1, 5.2, 5.3, 6.4_

- [x] 4. Good-citizen fetch layer [PERMANENT]
  - [x] 4.1 Implement `adapters/ventura/fetch.py`
    - Done. Permitted-host allowlist + off-domain redirect block (SSRF/§34); descriptive UA; conditional GET (If-Modified-Since/If-None-Match, 304 handling); process-wide lock for max-1-concurrent; exponential backoff on 429/503; every failure logged, never swallowed.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 6.5_
  - [x] 4.2 Unit test: allowlist blocks the Granicus host and off-domain redirects [TEST]
    - Done. 5 tests: permitted passes, Granicus refused, arbitrary host refused, off-domain redirect blocked, same-host redirect allowed.
    - _Requirements: 7.1_

- [x] 5. Meeting enumeration from the combined index [PERMANENT]
  - [x] 5.1 Implement `adapters/ventura/enumerate.py`
    - Done. Parses combined index HTML → MeetingStubs; attributes each to a body via nearest header + registry; meeting date from `_MMDDYYYY`; unknown body → surfaced (body_id=None), never dropped; malformed row → logged + skipped. Verified against real fixture: 129 meetings, City Council attributed, meeting 3569 date correct.
    - _Requirements: 2.1, 2.2, 2.4_
  - [x] 5.2 Property test: index parser robustness [TEST]
    - Done. Never-crashes property + real-fixture invariant (every emitted meeting has date + ≥1 doc URL). `# Feature: 1-ventura-adapter, Property 3`.
    - _Requirements: 2.1, 2.2_

- [x] 6. PreviousVersions version trail [PERMANENT]
  - [x] 6.1 Implement `adapters/ventura/previous_versions.py`
    - Done. Parses PV page → classified DocumentRefs; unclassified surfaced; verified against real fixture (meeting 3569): ≥5 docs incl. agenda-type + minutes. Horizon gate is the caller's responsibility (documented).
    - _Requirements: 2.3, 3.2, 3.3_

- [x] 7. Body registry [PERMANENT]
  - [x] 7.1 Create `adapters/ventura/registry.py` — body names/identifiers + verification date
    - Done. 21 bodies (exact rendered names), owner=shara, verified 2026-08-27. `body_for_name` returns None for unknown → caller surfaces, never fabricates.
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 9.2_

- [x] 8. Honest states and failure logging [PERMANENT]
  - [x] 8.1 Wire absence string and per-body isolation
    - Done at the module level: enumerate/PV log-and-continue per row/anchor (no whole-parse failure); unknown body surfaced; fetch logs every failure. The literal absence string `not located at [url] as of [timestamp]` is a rendering concern used by the pipeline/UI layer (Spec 2/6); the adapter produces the structured facts that feed it. Copied-not-generated is enforced (dates from URL/source, names from registry).
    - _Requirements: 2.5, 6.1, 6.2, 6.3, 6.5_

- [x] 9. Fixtures from real Ventura documents [TEST]
  - [x] 9.1 Save a small real fixture set into `tests/fixtures/`
    - Done. `tests/fixtures/ventura/agenda_center_index.html` (525 KB, real combined index, 129 meetings) and `previous_versions_3569.html` (154 KB, real amendment trail with multiple ArchivedAgenda versions). Cancellation and amended examples are present in the index text ("**CANCELLED** ...", "Amended ...").
    - **FINDING — Spanish edition is NOT dead code:** Ventura DOES publish its own Spanish agendas (21 Spanish titles in the real index, e.g. "10 DE FEBRERO DE 2026 AGENDA DEL CONCEJO MUNICIPAL"). So `spanish_edition` (R3.4) is exercised by real data; no synthetic fixture was fabricated. Note for README/§8: Ventura publishes city Spanish editions distinct from our translation surface — both exist; the classifier tags the city's, §8 generates ours.
    - _Requirements: pass gate 3, 3.4_

- [x] 10. VERIFICATION: correct meeting list for a known week [VERIFICATION]
  - [x] 10.1 Hand-check City Council and Planning Commission for a known week against the live site
    - RESULT: parser's recent CC meetings (3685 Aug-25, 3680 Aug-18) and PC meetings (3687 Aug-26, 3682 Aug-20) all resolve to live `application/pdf` agendas (HTTP 200). Included a meeting with a Spanish edition (§36): Apr-28 has English `3621` and Spanish `3622`, both resolve live, both attributed to City Council by date. Pass gate 1 met.
    - BUG FOUND + FIXED during hand-check: every stub carried duplicate document URLs (rows link the same file twice, icon + text anchor). Fixed `enumerate.py` to de-dupe URLs within a row; CC 3685 now shows the correct Agenda+Minutes, 0 stubs with duplicates.
    - COUNT CORRECTION (was wrong in the first wave-6 report): the 129→152 change is NOT site growth. Re-parsing the UNCHANGED saved fixture with the current parser yields 152, so the parser changed, not the site. The 129 was wave-0's count of `PreviousVersions` links only; the parser correctly emits any row with a meeting link. The extra 23 are 129 PV-linked rows + 23 rows that have a `ViewFile/Agenda` link but no PV link. Verified they are REAL meetings, not header/empty artifacts: all sampled resolve to live HTTP 200 agendas; classified as 9 spanish_edition, agenda, supplemental, cancellation. This is the better of the two explanations — real meetings we would have dropped under the old count, not phantom meetings Spec 2 would ingest.
    - §36 note: the Spanish edition has a DIFFERENT meeting id than its English counterpart (3622 vs 3621), matched by date. Same-meeting linking is Spec 3/6 work per §36b, not built here.
    - FLAG for Spec 3 (§36b), recorded not built: EN/ES pairing must match on **body_id + date**, not date alone. Two bodies meeting the same day, both with Spanish editions, would cross-link under date-only matching. (Owner: recorded here for the decisions-doc §36b; do not implement in Spec 1.)
    - _Requirements: pass gate 1_

- [x] 11. VERIFICATION: stale-agenda behavior [TEST]
  - [x] 11.1 Out-of-horizon document rejected before fetch; amended-after-meeting ingested but not surfaced
    - Covered by the horizon property tests: `in_horizon` false outside [-14d, +30d] (rejects before fetch, the gate runs before PV/PDF fetches by design); `is_upcoming` false for a past meeting regardless of when its amendment posted (post-meeting amendment ingested-if-in-horizon but never upcoming). 17 horizon/classify tests + enumerate tests green.
    - _Requirements: 4.2, 4.3, 5.2_

- [ ] 12. (moved to 0.1 — posting lead time runs in wave 0, before code)

- [x] 13. Final checkpoint
  - RESULT: full suite 57 passed, 3 deselected. Clean-clone setup verified from a temp-dir clone: plain `uv sync` leaves pytest absent; `uv sync --extra dev` → 57 pass. README updated: setup uses `--extra dev` with the reason; headline pairs median+floor ("about five days to act, sometimes the same day"); §36 Spanish (~1 in 6 city-published, shown in preference, labeled differently); reusability scoped to CivicEngage AgendaCenter (§34/R9.1); robots.txt-as-convention paragraph stated plainly (§34b); §35g same-day gap left visible, not solved.
  - Pass gates: (1) meeting list hand-checked ✓; (2) stale-agenda tests ✓; (3) role classification on real roles ✓; (4) property tests on parser + horizon ✓; (5) posting lead time measured, median 5d / min 0d ✓.
  - _Requirements: 9.1, 9.3, pass gate 1–5_

## Notes

- Thresholds T1–T14 are named in requirements.md R8 with proposed values; they are
  finalized at Spec 2 close, not here. Ordering constraint `T11 < T12 < T14` holds.
- The "packet" → "agenda" vocabulary correction (§35a) applies to new code and
  spec language here; the mock copy sweep is Spec 6 (§35d), not this spec.
- Property tests use Hypothesis. Tag format: `# Feature: 1-ventura-adapter, Property {N}: {title}`.
- **§28 confirmation (dedup bug, task 10.1):** the property tests passed while the
  real output was wrong. Every stub carried duplicate document URLs and the whole
  test suite was green; only the hand-check against the live site caught it. This
  is exactly why the hand-check gate exists — green tests are not proof of correct
  output on real data.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2", "1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 3, "tasks": ["4.2", "5.1", "7.1"] },
    { "id": 4, "tasks": ["5.2", "6.1", "8.1"] },
    { "id": 5, "tasks": ["9.1"] },
    { "id": 6, "tasks": ["10.1", "11.1"] },
    { "id": 7, "tasks": ["13"] }
  ]
}
```
