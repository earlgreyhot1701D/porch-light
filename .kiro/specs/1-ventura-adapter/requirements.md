# Requirements Document — Spec 1: Ventura Adapter

## Introduction

Spec 1 builds the deterministic adapter that turns the City of Ventura's public
meeting pages into structured records: which bodies exist, which meetings they
held or will hold, and which documents (agenda, amended, supplemental,
cancellation notice, Spanish edition, minutes) belong to each meeting. It does
**not** read packet contents or extract items — that is Spec 2/3. Spec 1 stops
at "here is the meeting, here is its agenda document, here is the page structure
needed to locate items later."

This is the layer civiq got wrong: it fetched stale agendas because it conflated
posting order with meeting chronology. The ingestion horizon and surfacing rules
(§7) are therefore requirements here, not niceties.

**Platform and compliance are settled in decisions §34** (CivicEngage
AgendaCenter on `www.cityofventura.ca.gov` is the permitted host; the Granicus
host `cityofventura.granicus.com` is `Disallow: /` and excluded, including its
`JSON.php` API). This spec references §34 and does not restate it. Coverage was
verified against a real meeting before this spec was written (see Verification
Findings below).

## Rigor budget (from style.md)

This is feature code, so **working rigor**: it must produce the right answer on
real Ventura inputs, checked by hand against the live site. **Property tests only
where a wrong answer would be invisible** — here that means the agenda-index
parser and the horizon/surfacing rules. No property tests on things a human can
verify by reading (URL construction, config lists, status strings).

## Verification findings that shape these requirements

Confirmed on the permitted host (`www.cityofventura.ca.gov`) across several real
meetings before writing this spec:

- The `Agenda` document resolves at `/AgendaCenter/ViewFile/Agenda/_<MMDDYYYY>-<id>`,
  returns `application/pdf`, carries a `Last-Modified` header, and has a real
  **text layer** (not scanned): meeting date, meeting type + city-local times,
  body name, numbered items, and section headers all present.
- The AgendaCenter index page **does server-render the full meeting list**: it
  contains `/AgendaCenter/PreviousVersions/_<MMDDYYYY>-<id>` links for every
  meeting (129 present at check time), plus current `ViewFile/Agenda` and
  `ViewFile/Minutes` links. An earlier read that suggested the list was
  JavaScript-only was from a truncated fetch and was wrong. The category filter
  controls are JS-rendered, but the meeting rows are in the served HTML. So
  enumeration does not require a headless browser.
- **The amendment/version trail lives one level down, in the `PreviousVersions`
  page per meeting, not in the index.** For meeting `_02102026-3569` that page
  lists multiple `ArchivedAgenda` versions (ids 3780, 3788, 3802, 3831, 3904) and
  the terms "Supplemental", "Attachment", "Packet", and "Cancel" all appear.
  Amended and supplemental material is therefore real and discoverable on the
  permitted host — via `PreviousVersions`, which is where R3 (role classification)
  and R5 (surfacing) must look.
- **Document size (corrected finding):** sampled agendas run 2–14 pages,
  ~150 KB–940 KB (ids 3573, 3571, 3568, 3561, 3569). These are agenda documents
  carrying item listings and staff-recommendation summaries, not 300-page
  consolidated packets. The earlier "no separate packet document" claim was
  inferred from two guessed URL patterns (`Packet`, `AgendaPacket`) returning 404
  and was not sound. The evidence-based statement is: **Ventura's per-meeting
  documents are modest agendas plus a version/supplemental trail in
  `PreviousVersions`; no single large consolidated packet was observed.** This is
  a product-sizing input: §11.5 cost lines, page-range receipts, and extractor
  caps should be sized for tens of pages per document, not hundreds, but the caps
  still exist because a supplemental or an outlier body could be larger, and that
  must be confirmed against more bodies at Spec 2/3, not assumed here.
- Whether a documented structured feed exists on the permitted host: **no**. The
  RSS endpoints probed (`RSSFeed.aspx`, `AgendaCenter/RSS`) return 404, and the
  only JSON API (`JSON.php`) is on the excluded Granicus host (§34c stands
  unchanged — no documented API available to us). Enumeration is server-rendered
  HTML on the permitted host, which is sufficient.
- **The "upcoming" window is narrow, permanently (§35e).** Measured 2026-08-27:
  the index's newest meeting was the prior day, and 0 of the 10 in-horizon
  meetings were in the future. AgendaCenter lists a meeting only once its agenda
  posts, and Ventura posts close to the meeting. So Porch Light promises "you will
  hear about it with about [measured] days to act," not "watch the calendar." The
  real lead time is a pass-gate measurement (below), not an assumption.
- **Per-body pages exist but are unreliable; the combined index is the source.**
  All four probed category slugs return 200, but Planning-Commission-6 renders its
  meetings server-side while City-Council-2 returns zero rows (JS-loaded). The
  combined `/AgendaCenter` index reliably renders all 129 for all bodies, so the
  registry (R1) is a list of body names, not URLs, and enumeration is one fetch.

## Glossary

- **Body**: a public legislative or advisory group with its own AgendaCenter page
  (e.g., City Council, Planning Commission, Design Review Committee, Historic
  Preservation Committee, and council advisory groups/committees).
- **Meeting**: one dated convening of a body, with one or more associated documents.
- **Document**: a single file attached to a meeting — agenda, amended agenda,
  supplemental packet, cancellation notice, Spanish edition, or minutes.
- **Document role**: the deterministic classification of a document (see R3).
- **Meeting date**: the date the body convenes. Distinct from posting date.
- **Posting date**: when a document appeared on the site. Never used for the horizon.
- **Ingestion horizon**: the window, computed from meeting date, outside which a
  document is not fetched (§7).
- **Surfacing rule**: the rule deciding whether an ingested document appears as
  "upcoming" (§7). Posting order is not chronology.
- **Permitted host / excluded host**: per §34 — `www.cityofventura.ca.gov` is
  permitted; `cityofventura.granicus.com` is excluded.
- **City local time**: America/Los_Angeles. Every rendered time is labeled with
  the zone and never silently converted (§2).

## Requirements

### Requirement 1: Body registry (deterministic, static config)

**User Story:** As the pipeline, I want the real list of Ventura public bodies
and their AgendaCenter URLs, so that the hunter has a fixed, inspectable set of
pages to check and nothing is discovered by guessing.

#### Acceptance Criteria

1. THE Adapter SHALL provide a static, versioned registry of Ventura public
   bodies, each entry containing: a stable `body_id`, the official body name
   (English), and the body's category (legislative / advisory). The registry is a
   list of body **names/identifiers**, NOT a list of per-body URLs: enumeration
   reads the single combined `/AgendaCenter` index and attributes each meeting to
   a body by that index's grouping (verified — per-body category pages exist but
   render inconsistently; the combined index reliably renders all bodies).
2. All fetching SHALL be on the permitted host (§34); no fetch SHALL target the
   excluded Granicus host. (The registry itself holds no URLs to validate; the
   host allowlist is enforced in `fetch.py`, R7.1.)
3. THE registry SHALL be verified by hand against the live AgendaCenter at build
   time, and the verification date recorded, because the roster changes (ad hoc
   committees are created and retired). A stale registry is a maintenance risk,
   not a silent failure: an unreachable body produces the honest empty state
   (R6), never a fabricated absence claim.
4. WHEN a body listed in the registry cannot be reached, THE Adapter SHALL report
   it as "not located at [url] as of [timestamp]" and SHALL NOT assert the body
   has no meetings. (never.md #3, #7.)
5. THE registry SHALL NOT include per-body counts, scores, or any aggregate.
   (never.md #2.)

### Requirement 2: Meeting enumeration (deterministic)

**User Story:** As the pipeline, I want to list the meetings for a body from the
server-rendered AgendaCenter HTML, so that enumeration is reproducible, testable,
and needs no headless browser.

#### Acceptance Criteria

1. THE Adapter SHALL enumerate meetings by parsing the **single combined**
   server-rendered `/AgendaCenter` index on the permitted host, which reliably
   contains a `PreviousVersions` link and current `ViewFile/Agenda` /
   `ViewFile/Minutes` links for every meeting of every body (129 verified). It
   SHALL NOT require executing page JavaScript or a headless browser, and SHALL
   NOT depend on per-body category pages (verified inconsistent: some render
   server-side, some load rows via JS). The category-filter widget on the index
   is JS-rendered and SHALL NOT be relied on.
2. FOR each enumerated meeting, THE Adapter SHALL capture: `body_id`, meeting
   date, meeting type (regular / special / adjourned / closed-session, as stated
   in the source), and the set of associated document URLs with their roles (R3).
3. THE Adapter SHALL follow each meeting's `PreviousVersions` page to discover the
   amendment/supplemental/version trail (`ArchivedAgenda`, `ArchivedMinutes`, and
   any supplemental/attachment entries), because that trail is not in the index —
   it is one level down. This is the source R3 and R5 depend on.
4. THE Adapter SHALL treat meeting date as authoritative from the document/source
   text, never inferred from the file name or the posting order.
5. IF enumeration for a body fails or returns nothing, THE Adapter SHALL emit the
   honest empty state for that body (R6) and continue with other bodies. One
   body's failure SHALL NOT fail the run.

### Requirement 3: Document role classification (deterministic, no model)

**User Story:** As the pipeline, I want each document classified by role using
pure code, so that a model never decides what a document is. (model-authority.md.)

#### Acceptance Criteria

1. THE Adapter SHALL classify each document into exactly one role: `agenda`,
   `amended_agenda`, `supplemental`, `cancellation`, `spanish_edition`, or
   `minutes`. Classification SHALL be a pure function of deterministic inputs
   (URL path, document-type segment, title text, language markers). No model.
2. THE Adapter SHALL detect a **cancellation** and record the meeting as
   cancelled without treating it as new agenda content.
3. THE Adapter SHALL detect an **amended** or **supplemental** document for a
   meeting that already exists and associate it with that meeting rather than
   creating a duplicate meeting.
4. THE Adapter SHALL detect a **Spanish edition** and link it to the same meeting
   as its English counterpart rather than recording it as a separate meeting.
   (civiq already solved Spanish-edition detection; §7.)
5. THE Adapter SHALL detect a **special meeting** and record its meeting type
   distinctly from a regular meeting, because special meetings carry different
   notice and comment rules.
6. WHEN a document's role cannot be determined with confidence, THE Adapter SHALL
   record it with an explicit `unclassified` marker and its URL, never guess a
   role, and surface it in the run log for human review. (Fail closed, §7.)
7. Document identity SHALL be a content hash, so the same file is always the same
   `document_id` and re-posting an identical file is idempotent (§7).

### Requirement 4: Ingestion horizon (deterministic guardrail)

**User Story:** As the operator, I want the adapter to refuse documents outside a
defined time window computed from the meeting date, so that civiq's stale-agenda
failure cannot recur.

#### Acceptance Criteria

1. THE Adapter SHALL compute the ingestion horizon from the **meeting date**,
   never the posting date and never the file name.
2. THE Adapter SHALL NOT fetch or record a document whose meeting date falls
   outside the horizon window (see thresholds T1, T2).
3. THE horizon check SHALL be enforced before any document body is fetched (at
   the hook layer per §3), so an out-of-window document is rejected before the
   fetch, not filtered after.
4. THE horizon window SHALL be a single configured value with a one-line
   rationale, not a magic number scattered in code (style.md).

### Requirement 5: Surfacing rule (deterministic guardrail)

**User Story:** As a watcher, I want an agenda amended after its meeting to be
recorded but never shown as upcoming, so that posting order never masquerades as
chronology.

#### Acceptance Criteria

1. THE Adapter SHALL distinguish "ingested" from "surfaced as upcoming." A
   document being ingested SHALL NOT imply it is upcoming.
2. WHEN a document is posted or amended for a meeting whose date has already
   passed, THE Adapter SHALL record it as new material for a past meeting and
   SHALL NOT surface it as upcoming. (Real case on the Ventura site, §7.)
3. THE surfacing decision SHALL be a pure function of the meeting **start
   datetime** versus the current city-local datetime. It SHALL use the meeting
   time extracted from the agenda text (e.g. "SPECIAL MEETING - 5:00 P.M."), not
   date granularity: a 5:00 PM meeting SHALL stop being "upcoming" at 5:00 PM, not
   at midnight. Because the product's job is to notify *before* a meeting starts,
   day granularity on the day of the meeting is a bug, not an approximation.
4. WHEN the meeting time cannot be parsed, THE Adapter SHALL fall back to
   end-of-day city-local for the upcoming decision AND SHALL log the fallback, so
   a day-granularity decision is never made silently.
5. "Upcoming" SHALL be computed against **city local time** (America/Los_Angeles),
   not the server clock or the viewer's zone (§2).

### Requirement 6: Honest states and time handling

**User Story:** As a user, I want absence and time stated honestly, so that a
quiet body and a broken fetch are never confused, and a deadline is never wrong.

#### Acceptance Criteria

1. Absence SHALL be expressed exactly as "not located at [url] as of [timestamp]",
   never "missing", "overdue", "late", "delayed", or "failed", in copy, code
   comments that render, or color. (never.md #3, voice.md.)
2. Every meeting date, meeting time, and any deadline the adapter captures SHALL
   be stored with an explicit timezone and rendered in city local time, always
   labeled with the zone, never silently converted to the viewer's zone (§2).
3. Dates, times, meeting-type labels, and body names SHALL be copied from source,
   never generated or paraphrased (never.md #1).
4. THE Adapter SHALL have an explicit DST-boundary test case for the city-local
   date/time logic (§2): a meeting at 5:00 PM city-local SHALL be upcoming at
   4:59 PM and not upcoming at 5:01 PM, on both a spring-forward and a fall-back
   date, regardless of the runner's zone or UTC.
5. A degraded dependency SHALL produce an honest empty state, never a fabricated
   or silently-degraded result (never.md #7).

### Requirement 7: Good-citizen fetch posture

**User Story:** As a public body's server, I want this reader to behave, so that
Porch Light earns the trust its whole premise depends on.

#### Acceptance Criteria

1. THE Adapter SHALL fetch only from the permitted host and SHALL block
   off-domain redirects rather than follow them (§34, SSRF rule in security.md).
2. THE Adapter SHALL send a descriptive User-Agent naming the project with a
   contact URL (`FETCH_USER_AGENT_CONTACT` in `.env.example`).
3. THE Adapter SHALL use conditional GET (honoring `Last-Modified` / `ETag`,
   confirmed present on agenda PDFs) so unchanged documents are not re-downloaded.
4. THE Adapter SHALL fetch at most one document at a time (max 1 concurrent),
   with exponential backoff on 429/503, and SHALL respect the crawl posture
   (hourly, not continuous — enforced by the Spec 2 scheduler, honored here).
5. THE Adapter SHALL obey `robots.txt` on the permitted host even though it is a
   convention, not law, because the product's claim is trustworthy reading of
   public records. (Rationale to be stated plainly in the README, per §34 note.)

### Requirement 8: Thresholds (fourteen values, each with a rationale)

**User Story:** As the operator, I want every tunable number named with a value
and a one-line rationale before Spec 2, so that no magic number is unlabeled.

These are the fourteen §16a-ii thresholds. Values are **proposed** (guessed is
fine, unlabeled is not) and finalized at Spec 2 close. Timeout ordering constraint
holds: **run timeout < lock TTL < schedule interval** (§7).

| # | Threshold | Proposed value | One-line rationale |
| --- | --- | --- | --- |
| T1 | Ingestion horizon — future window | 30 days ahead | CORRECTED from 90 days, which contradicted its own rationale. Ventura posts agendas close to the meeting (regular agendas ~72 hours out; special meetings on shorter notice), so agenda content rarely exists more than a few weeks ahead. 30 days covers realistic scheduling lead time with margin while excluding far-future placeholder calendar entries that carry no agenda. The 72-hour figure is posting lead time, not the horizon; the horizon is the window of meetings we care about. |
| T2 | Ingestion horizon — past window | 14 days back | Long enough to catch an agenda amended shortly after its meeting (the real §7 case); short enough that the backfill is not unbounded. |
| T3 | Dormancy threshold (site) | 36 hours since last successful read | Beyond ~1.5 days of silence the "quiet because nothing happened" vs "quiet because broken" ambiguity must resolve toward the honest broken state (§16b). |
| T4 | Circuit-breaker failure percentage | 50% of a body's fetches failing in one run | Half a body's documents failing signals a site-side problem, not one bad file; trip and report rather than hammer. |
| T5 | Quarantine consecutive-failure count | 3 consecutive failed runs for one document | civiq/§16 layer-4 value; three strikes distinguishes a transient blip from a genuinely unreadable document. |
| T6 | HTTP fetch timeout | 30 seconds | A single PDF (~1 MB observed) should return well under this; longer means the server is struggling, so give up and back off. |
| T7 | Tool-call timeout | 45 seconds | One hook-wrapped tool operation; slightly above the fetch timeout so the fetch's own timeout fires first. |
| T8 | Model-call timeout | 60 seconds | Not used in Spec 1 (no model here); recorded for ordering completeness, finalized when the rewrite lands (Spec 3). |
| T9 | Agent-invocation timeout | 120 seconds | One hunter loop over a body's documents; bounds a single body's work. |
| T10 | Per-document timeout | 90 seconds | Fetch + hash + classify for one document; above the fetch timeout, below the agent-invocation timeout. |
| T11 | Whole-run timeout | 10 minutes | Bounds a full pass over all bodies; must stay under the lock TTL (T12). |
| T12 | Run-lock TTL | 15 minutes | Above the run timeout (T11) so a live run never loses its own lock; below the schedule interval (T14) so a dead run cannot deadlock the schedule. |
| T13 | Max documents per body per run | 50 | Far above any real body's per-run document count; a runaway past this signals a parsing bug, so cap and report. |
| T14 | Schedule interval | 60 minutes | Hourly, per §7 good-citizen posture; larger than the lock TTL (T12) so runs never overlap. |

Note: T8 (model-call) and T14 (schedule interval) live operationally in Spec 2/3
but are listed here so the full fourteen are named in one place with the ordering
constraint visible, per §16a-ii.

### Requirement 9: Maintenance and reusability honesty

**User Story:** As future maintainer and as a judge, I want the adapter's scope
claim and its rot points stated honestly.

#### Acceptance Criteria

1. THE Adapter SHALL be built as a **CivicEngage AgendaCenter** adapter, not a
   "CivicPlus" adapter and not a Ventura-only adapter (§34 corrected the vendor
   name). The reusability claim SHALL be scoped to CivicEngage AgendaCenter
   cities, and the README SHALL NOT overstate it.
2. THE body registry (R1) is a rot point: it SHALL have a named owner and a
   recorded verification date, per §11 maintenance rules.
3. THE README SHALL state plainly that Porch Light obeys the Granicus `robots.txt`
   block even though robots.txt is a convention, because a civic-trust product
   that overrides a public body's stated crawl preference has a findable hole in
   its own story (§34 note). This is a Design and Potential Impact point.

## Pass gate for this block

1. The correct meeting list for a known week, checked **by hand** against the live
   AgendaCenter, for at least City Council and Planning Commission.
2. Stale-agenda tests passing: an agenda amended after its meeting date is
   ingested but not surfaced as upcoming (R5), and a document outside the horizon
   is rejected before fetch (R4).
3. Document role classification correct on real examples of each role that exists
   in Ventura's data: agenda, amended, supplemental, cancellation, Spanish
   edition, minutes.
4. Property tests present and passing on the two invisible-failure surfaces: the
   agenda-index parser and the horizon/surfacing rules.
5. **Posting lead time measured (§35e):** across at least 20 real meetings, agenda
   `Last-Modified` versus meeting date, reporting the **median and minimum**. This
   number is the README's honest headline ("about N days to act") and the basis
   for the Spec 5 watch cadence. Not assumed — measured.

## Explicitly out of scope for Spec 1

- Reading packet contents or extracting items / page ranges (Spec 2/3).
- Any model call (Spec 3).
- The scheduler, run lock, and queue mechanics (Spec 2) — Spec 1 honors their
  constraints but does not build them.
- Storage schema beyond what the adapter needs to hand off (Spec 2 owns `db/`).
