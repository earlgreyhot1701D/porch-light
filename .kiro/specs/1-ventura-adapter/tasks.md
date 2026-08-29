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

- [ ] 2. Document role classifier [PERMANENT]
  - [ ] 2.1 Implement `adapters/ventura/classify.py` — pure `classify(ref) -> Role`
    - Signals per design table: current Agenda, ArchivedAgenda-with-newer → amended, supplemental/attachment label, cancellation marker, Spanish markers, Minutes; else `unclassified`.
    - No network I/O, no model. Amended/supplemental/Spanish all associate to the existing meeting id, never a new meeting.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [ ] 2.2 Property test: classifier never guesses, never crashes [TEST]
    - **Property: unmatched input → `unclassified`; no role returned whose signal is absent; no exception on arbitrary input.**
    - Tag: `# Feature: 1-ventura-adapter, Property 1: classifier soundness`
    - _Requirements: 3.1, 3.6_

- [ ] 3. Ingestion horizon and surfacing rule [PERMANENT]
  - [ ] 3.1 Implement `adapters/ventura/horizon.py` — `in_horizon()` and `is_upcoming()`
    - `in_horizon`: meeting date within `[today - T2, today + T1]`, computed from meeting date not posting date.
    - `is_upcoming`: compares against meeting **start datetime** (city local); uses parsed meeting time; falls back to end-of-day AND logs the fallback when time is unknown.
    - All in America/Los_Angeles.
    - _Requirements: 4.1, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5_
  - [ ] 3.2 Property test: horizon + surfacing correctness including DST [TEST]
    - **Property: `in_horizon` monotonic in date; a post-meeting amendment is never `upcoming`; a 5:00 PM meeting is upcoming at 4:59 PM and not at 5:01 PM on BOTH spring-forward and fall-back dates, independent of runner zone/UTC.**
    - Tag: `# Feature: 1-ventura-adapter, Property 2: horizon and surfacing`
    - _Requirements: 4.1, 5.2, 5.3, 6.4_

- [ ] 4. Good-citizen fetch layer [PERMANENT]
  - [ ] 4.1 Implement `adapters/ventura/fetch.py`
    - Host allowlist = permitted host only; off-domain redirects blocked, not followed (SSRF).
    - Descriptive User-Agent from `FETCH_USER_AGENT_CONTACT`; conditional GET (`Last-Modified`/`ETag`); max 1 concurrent; exponential backoff on 429/503.
    - Every fetch failure writes to the failure log (no silently swallowed exception).
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 6.5_
  - [ ] 4.2 Unit test: allowlist blocks the Granicus host and off-domain redirects [TEST]
    - Working-rigor test with a stubbed redirect; asserts the excluded host is refused.
    - _Requirements: 7.1_

- [ ] 5. Meeting enumeration from the combined index [PERMANENT]
  - [ ] 5.1 Implement `adapters/ventura/enumerate.py`
    - Parse the single combined `/AgendaCenter` served HTML; attribute each meeting to a body; capture body_id, meeting date (from `_MMDDYYYY`, cross-checked against PDF text), meeting type (from PDF first-page text), current Agenda/Minutes URLs.
    - Does not execute JS; does not depend on per-body pages.
    - _Requirements: 2.1, 2.2, 2.4_
  - [ ] 5.2 Property test: index parser robustness [TEST]
    - **Property: parser never crashes on malformed/partial rows; every emitted meeting has a valid date and at least one document URL; a row it cannot parse is surfaced, not dropped silently.**
    - Tag: `# Feature: 1-ventura-adapter, Property 3: index parser`
    - _Requirements: 2.1, 2.2_

- [ ] 6. PreviousVersions version trail [PERMANENT]
  - [ ] 6.1 Implement `adapters/ventura/previous_versions.py`
    - For each in-horizon meeting, fetch and parse its PreviousVersions page → full document set (ArchivedAgenda*, ArchivedMinutes*, supplemental/attachment entries) with roles via `classify`.
    - Horizon gate (task 3) runs BEFORE this fetch.
    - _Requirements: 2.3, 3.2, 3.3_

- [ ] 7. Body registry [PERMANENT]
  - [ ] 7.1 Create `adapters/ventura/registry.py` — body names/identifiers + verification date
    - List of `body_id` + official English name + category. NOT URLs (enumeration uses the combined index).
    - Named owner and hand-verification date recorded (§11 maintenance).
    - Unreachable/absent body → honest empty state, never a fabricated absence.
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 9.2_

- [ ] 8. Honest states and failure logging [PERMANENT]
  - [ ] 8.1 Wire absence string and per-body isolation
    - Absence rendered exactly `not located at [url] as of [timestamp]`; one body's failure never fails the run; dates/times/labels/names copied from source, never generated.
    - _Requirements: 2.5, 6.1, 6.2, 6.3, 6.5_

- [ ] 9. Fixtures from real Ventura documents [TEST]
  - [ ] 9.1 Save a small real fixture set into `tests/fixtures/`
    - Include one amended meeting and one cancellation; agenda with a text layer.
    - **Spanish edition: use one ONLY if it exists in real Ventura data. Do NOT fabricate a synthetic Spanish fixture to make a test pass** (that is the §28 failure mode with better manners). If none exists: mark R3.4's `spanish_edition` role as unexercised dead code with a comment naming why it exists (other CivicEngage cities publish them), and note for the README that Porch Light's Spanish surface is our translation of English source (§8), not the city's own Spanish edition — an honest limitation.
    - Tests run offline against these; live checks are marked and run deliberately.
    - _Requirements: pass gate 3, 3.4_

- [ ] 10. VERIFICATION: correct meeting list for a known week [VERIFICATION]
  - [ ] 10.1 Hand-check City Council and Planning Commission for a known week against the live site
    - RESULT recorded here (pass gate 1).
    - _Requirements: pass gate 1_

- [ ] 11. VERIFICATION: stale-agenda behavior [TEST]
  - [ ] 11.1 Out-of-horizon document rejected before fetch; amended-after-meeting ingested but not surfaced
    - Working-rigor tests on real fixtures (pass gate 2).
    - _Requirements: 4.2, 4.3, 5.2_

- [ ] 12. (moved to 0.1 — posting lead time runs in wave 0, before code)

- [ ] 13. Final checkpoint
  - All property tests and working-rigor tests pass. Pass gates 1–5 met. README claim scoped to CivicEngage AgendaCenter (not "CivicPlus", not "Ventura-only"); robots.txt-as-convention rationale stated plainly (§34 note); "about N days to act" headline uses the measured median.
  - _Requirements: 9.1, 9.3, pass gate 1–5_

## Notes

- Thresholds T1–T14 are named in requirements.md R8 with proposed values; they are
  finalized at Spec 2 close, not here. Ordering constraint `T11 < T12 < T14` holds.
- The "packet" → "agenda" vocabulary correction (§35a) applies to new code and
  spec language here; the mock copy sweep is Spec 6 (§35d), not this spec.
- Property tests use Hypothesis. Tag format: `# Feature: 1-ventura-adapter, Property {N}: {title}`.

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
