# Requirements Document — Spec 3: Extraction, Rewrite, and the Verifier

## Introduction

Spec 3 is where the model finally does its job, and where the product becomes
something a person sees. It turns a stored agenda document into structured items
with page ranges (the extractor), rewrites each item's staff language into plain
English and Spanish (the rewrite chain), and proves every rewrite against the
source with a deterministic six-check verifier before it can be shown. It also
assembles the structure of a public-comment draft — facts and receipts only,
never a stance. And it decides the production model on measured evidence.

This is the block the build plan flagged as the fullest and the most likely to
slip. Two guards against that are requirements here, not afterthoughts: the demo
video script is drafted in this block (if the product cannot be narrated in five
minutes, scope is cut now while cutting is cheap), and the verifier's six checks
each get property tests (a verifier that passes a bad rewrite is the worst kind of
invisible failure — §28).

References §2 (the model's three jobs), §3 (extractor loop, cap 6, no egress), §4
(the six-check verifier), §4b (draft = structure, never stance), §11 (golden set,
poisoned PDF), §21 (bilingual chain + post-hoc-explanation ban), §25 (contract-first
fixtures), §27 (model selection on measured evidence), §30d/§38 (extractor is a
separate AgentCore runtime with no egress), §35a (agenda not packet), §36b (EN/ES
pairing on body_id + date), §39 (carry-forwards: our-run-log window, Cost Explorer
cost). The `never.md` and `model-authority.md` rules govern throughout.

## Rigor budget (style.md)

Feature code with a model in the loop, so **working rigor on real Ventura
agendas**, plus **property tests on the two invisible-failure surfaces: the six
verifier checks, and the extractor's page-range/entity extraction.** The verifier
is the product's spine — a false pass ships a fabricated summary with a receipt,
which is worse than no summary. Model output is tested against captured real
documents and the golden set, never against a description of what the model
"should" return (testing.md).

## Glossary

- **Item**: one agenda item, with an item number, a page range, and text, all
  copied from the source (never model-generated) (§2, never.md #1).
- **Extractor**: the AgentCore agent that reads one document and produces items.
  Cap 6 turns, hard token cap, **no network egress** (§3, §30d, §38).
- **Rewrite**: the model turning staff language into plain English, then the
  verified English into Spanish (§21 chain).
- **Verifier**: six deterministic checks, pure code, run on every rewrite (§4).
- **Draft scaffold**: the structure of a public comment — facts + receipt +
  logistics filled, stance fields empty by construction (§4b).
- **Golden set**: ~20 items hand-extracted from real Ventura agendas, checked by
  eye, the measurement baseline (§11).
- **Receipt**: body, meeting date, item number, page range, source link (§6, never.md #6).

## Requirements

### Requirement 1: Extractor — items with page ranges (the agent, no egress)

**User Story:** As the pipeline, I want one document turned into structured items
with accurate page ranges, so that every downstream claim can point at a page.

#### Acceptance Criteria

1. THE Extractor SHALL be an AgentCore agent (Strands) that reads ONE document per
   invocation and emits items, each with an item number and page range **copied
   from the source text, never generated** (§2, never.md #1).
2. THE Extractor SHALL run in its OWN AgentCore runtime with **no network egress
   at all** (§30d, §38): it reads document bytes/text passed to it or from storage,
   never fetches. This is a separate runtime from the hunter (which is a Lambda
   with egress) — networkMode is per-runtime, so egress-none is enforced at the
   runtime, plus the tool allowlist at the Strands hook layer (two independent
   layers, §security).
3. THE Extractor SHALL have a **hard turn cap of 6 and a hard token cap**, both of
   which demonstrably fire on an oversized document, and the firing is logged and
   surfaced (§3). A cap firing is a feature, not an error.
4. THE Extractor's tools SHALL be allowlisted at the Strands hook layer; a blocked
   tool call (e.g. an injected instruction to fetch a URL) is logged as a
   NEVER-trip (§security, never.md #9). Packet text is untrusted data, never
   instruction.
5. Output containing an item number or page range absent from the source SHALL be
   rejected before storage (§3). Item identity anchors to the extraction record,
   not to any later model call.
6. WHEN a document has no text layer (image-only scan), THE Extractor SHALL mark it
   unreadable with the reason and the source link, never guess (§7, §16b). This is
   a permanent failure (Spec 2 R5.2), not a retry.
7. WHEN the turn or token cap fires mid-document (a partially-extracted agenda),
   THE Extractor SHALL **keep the items already extracted** (they are real and
   verifiable) and mark the document **partially read**, with the reason and the
   source link, so a person knows to open the PDF for the rest. It SHALL NOT
   discard the partial items silently, and SHALL NOT present a partial extraction
   as complete (§16b eleventh failure state — silently showing partial as complete
   is exactly what §16b exists to prevent). The partial marker is shown alongside
   the real items, never instead of them.

### Requirement 2: The rewrite chain (source → EN → verify → ES → verify)

**User Story:** As a reader, I want the plain-language summary to say exactly what
the source says, in whichever language I read, so that I can trust it enough to act.

#### Acceptance Criteria

1. THE Rewrite SHALL be a chain (§21a): source → plain-English rewrite → verify
   against source → translate the VERIFIED English to Spanish → verify the Spanish
   against the ORIGINAL source (not against the English). Both language outputs are
   verified against the original document, never one against the other.
2. THE Rewrite call SHALL run at temperature ~0, structured output, **no tools, no
   loop** — it is a rewrite, not an agent action (§model-authority). Whether it
   goes through Strands or direct Converse is decided at the start of this block on
   the evidence (§27), not assumed.
3. THE Rewrite SHALL NOT generate or alter any date, deadline, item number, page
   range, body name, or URL (never.md #1). Those are attached from the extraction
   record (containment, §4 check 4).
4. WHERE the city published its OWN Spanish edition of a meeting (§36), THE System
   SHALL show the city's Spanish document and point the receipt at it, and SHALL
   NOT run our translation chain over that meeting's source. Our machine Spanish
   next to a link to a different official Spanish document would be a broken
   receipt. EN/ES pairing of a city meeting to its Spanish edition matches on
   **body_id + meeting date, not date alone** (§36b) — two bodies meeting the same
   day must not cross-link.
5. A model call SHALL NEVER consume another model call's output as source (§21d).
   The one exception is the ES-translates-verified-EN stage, which still verifies
   against the original source (§21a).

### Requirement 3: The six-check verifier (deterministic, pure, the spine)

**User Story:** As the project, I want every rewrite proven against its source by
code the model cannot influence, so that a fabricated or drifted summary never
reaches a person.

#### Acceptance Criteria

1. THE Verifier SHALL be **pure deterministic code, not a model** (§4,
   model-authority). The model never grades its own output.
2. THE Verifier SHALL run all six checks on every rewrite, in both languages:
   - **Check 1 — schema:** output has the required structure before anything else runs.
   - **Check 2 — entity preservation:** every number, date, dollar amount, street
     name, and proper noun in the output is present in the source page range,
     compared on **normalized** entities (Requirement 3a), not raw strings.
   - **Check 3 — no new entities:** any entity in the output absent from the source
     (after normalization) fails.
   - **Check 4 — containment:** item number, page range, deadline, and body are
     attached from the extraction record, never read from model output.
   - **Check 5 — reading level and length:** if it did not get simpler, it did not
     do its job. Reading level is measured **per language with a language-specific
     metric** (Requirement 3b) — an English metric on Spanish text is meaningless.
   - **Check 6 — both languages:** the Spanish rewrite passes the same normalized
     entity check against the same (English) source. Because comparison is on
     normalized entities, "February 10, 2026" and "10 de febrero de 2026" match;
     "$1.2 million" and "$1.2 millones" match; a street or body name that changed
     in translation does NOT match and fails, which is correct.
3. On the FIRST failure, THE Verifier SHALL retry the rewrite ONCE with the failure
   reason attached (a retry is code deciding after checking, not a loop — §4,
   model-authority). On the SECOND failure, THE System SHALL **show the original
   staff language with a note**, never a fabricated summary (§4, never.md #7).
4. Verifier rejection counts SHALL be recorded and surfaced ("3 items could not be
   summarized reliably, showing original text") — a trust feature, and the metric
   that decides model selection (§27).
5. **Each of the six checks SHALL have property tests** (rigor budget): a check
   that passes a rewrite it should reject is invisible failure of the worst kind.
   Tests use captured real documents and hand-built adversarial cases (a rewrite
   with an added entity, a dropped date, an altered dollar amount, an unsimplified
   copy, a Spanish rewrite with a changed number).

### Requirement 3a: The entity normalizer (pure, its own invisible-failure surface)

**User Story:** As the verifier, I want entities compared by meaning not by
spelling, so that a correct Spanish rewrite passes and a drifted one still fails.

The rule (the design decision requested): **entity classes split into NORMALIZE
and COMPARE-RAW.**

- **NORMALIZE (canonicalize both source and output before comparing)** — these
  legitimately change surface form across languages/formats while meaning is
  preserved:
  - **dates** → ISO 8601 (`February 10, 2026`, `10 de febrero de 2026`, `2/10/26`
    → `2026-02-10`).
  - **numbers / currency / percentages** → numeric value + unit token (`1.2
    million`, `1.2 millones`, `1,200,000`, `$1,200,000` → `1200000` with a currency
    flag; `5%` → `5 pct`).
- **COMPARE RAW (must be byte-identical, never translated)** — these are the fields
  a mistranslation must be caught on:
  - **proper nouns, person names, street names, body names.** A street name or a
    body name that changed in translation is a REAL failure, and check 6 must catch
    it, so these are compared raw. (E.g. "Main Street" must not become "Calle
    Principal" in a receipt-bearing summary.)

#### Acceptance Criteria

1. THE Normalizer SHALL be its OWN pure module (`verify/normalize.py`), no model,
   no I/O.
2. THE Normalizer SHALL canonicalize dates and numbers/currency/percentages to a
   comparable form across English and Spanish, and SHALL leave proper nouns / names
   / street names / body names raw for exact comparison.
3. THE Normalizer SHALL have **property tests**: it is an invisible-failure surface
   in both directions — over-normalization hides real drift (a changed number that
   canonicalizes to the same value would be a bug in the extractor, not the
   rewrite, but the normalizer must not mask a genuinely different value), and
   under-normalization fails correct Spanish. Tests assert: equivalent
   date/number forms across both languages normalize equal; a genuinely different
   number does NOT; a translated proper noun does NOT match (stays raw).
4. The rule (which classes normalize vs compare-raw) SHALL be documented in the
   module and the README, because it is a correctness-defining decision.

### Requirement 3b: Reading level, per language (Check 5)

**User Story:** As a reader, I want "did it get simpler" measured with a metric
that means something in my language.

#### Acceptance Criteria

1. English reading level SHALL use an English metric (Flesch-Kincaid or
   Flesch Reading Ease) with a stated threshold.
2. Spanish reading level SHALL use a **Spanish-calibrated metric** (Fernández
   Huerta or INFLESZ) with its OWN threshold, never the English number applied to
   Spanish text.
3. IF no defensible Spanish metric exists in a pinnable Python library, THE System
   SHALL fall back to a simpler language-agnostic proxy (mean sentence length +
   clause count) with a stated threshold, and the README SHALL state the limitation
   plainly (an honest weaker check beats a confident wrong one). Report which was used.

### Requirement 4: The draft scaffold (structure, never stance)

**User Story:** As a resident, I want the draft to carry the facts and the receipt
and leave the position to me, so that it is honestly mine and never a machine's opinion.

#### Acceptance Criteria

1. THE Draft scaffold SHALL contain only: the item and what it is, the receipt
   (body, meeting date, item number, page range, PDF link), the meeting logistics,
   how and where to submit comment, and the deadline in city local time (§4b).
2. THE stance fields SHALL be **empty by construction** — "your position", "why
   this matters to you", "what you are asking for" are labeled blanks the human
   fills. There is nothing for injected text to steer (§4b, never.md #5).
3. THE model SHALL NEVER generate a position, recommendation, persuasive argument,
   consequence claim, or characterization of motive (§4b, never.md #5). This is the
   most severe model-authority failure available in the build.
4. Every factual element in the scaffold SHALL pass the §4 verifier; nothing in the
   draft that is not in the source (§4b).
5. There SHALL be no send capability anywhere — not a stub, not a flag, not a dead
   path (never.md #4). The human sends.

### Requirement 5: Model selection on measured evidence (§27)

**User Story:** As the owner, I want the production model chosen by numbers, not
by which cloud is hosting the hackathon, so that the choice is defensible.

#### Acceptance Criteria

1. THE production model SHALL be chosen at this block on two measured numbers:
   **verifier rejection rate on identical real agendas**, and **measured cost per
   agenda** (§27), run against a wide sample (§39 — the cheaper 2–14-page documents
   make a wide sample affordable).
2. THE comparison SHALL run at least Amazon Nova Lite (the Spec 0 proven model)
   against one stronger model (e.g. a Claude model) on the SAME agendas, and record
   both numbers. **The sample is the golden set of ~20 hand-checked items (§11)** —
   countable and reproducible, so the comparison can be re-run and audited. "Wide"
   is affordable because the documents are 2–14 pages (§39), but the fixed,
   hand-verified golden set is what makes the rejection-rate number trustworthy.
3. THE model id SHALL be read from configuration, never hardcoded, and SHALL appear
   in every structured log event, so measurement runs are attributable (§27,
   Requirement 12 of Spec 0).
4. A deliberate, documented, config-level model choice is NOT the silent fallback
   `never.md` bans; there is no silent fallback to another provider (§20f, never.md
   #7). The test: a human chose it and wrote down why.
5. The chosen model, both numbers, and the rationale SHALL be recorded (README /
   decisions), and this becomes a builder.aws.com post (§11).

### Requirement 6: Contract-first fixtures and the mock-to-real seam (§25)

**User Story:** As the developer, I want the view contract defined and the mock
reading real-shaped fixtures, so that Spec 6 is a path swap and not a rebuild.

#### Acceptance Criteria

1. WHEN extraction first produces real items, THE System SHALL define the **view
   contract** (the JSON the web layer consumes) and convert the mock to read
   `fixtures/sample.json` conforming to it (§25). Chrome strings stay in COPY;
   item content comes from the fixture.
2. THE System SHALL ship `fixtures/ugly.json`, **generated by a script from real
   ingested data** (not hand-typed — testing.md #3), deliberately hostile: the
   longest real body name, an unrewritten item (verifier failed twice → original
   staff text), an unreadable document, a missing Spanish edition, a null deadline,
   an item with no clean page range, and a summary at the 95th percentile of real
   length. The 95th-percentile figure is computed and recorded in the fixture header.
3. A layout that survives both fixtures is wired-ready. Any category with no real
   instance yet is marked `synthetic: true` in the fixture so the gap is visible.

### Requirement 7: Deadline rendering (city local time, always labeled)

**User Story:** As a watcher who might be traveling, I want deadlines in the city's
time and clearly labeled, so that I never miss one by a timezone.

#### Acceptance Criteria

1. Deadlines and meeting times SHALL be stored with an explicit timezone and
   rendered in **city local time (America/Los_Angeles), always labeled with the
   zone**, never silently converted to the viewer's zone (§2, voice.md). This logic
   is built here (moved earlier from Spec 6, §25d) because the fixtures need real
   rendered values.
2. Relative phrasing ("closes tomorrow at 5") SHALL be computed against city time,
   with an explicit DST-boundary test case (§2). Deadlines are copied from source
   or not shown, never generated (never.md #1).

### Requirement 8: Prompt-injection containment, demonstrated (§11)

**User Story:** As the project, I want a real poisoned document in the repo with a
passing containment test, so that "we read untrusted PDFs safely" is proven, not asserted.

#### Acceptance Criteria

1. THE Repo SHALL contain a deliberately poisoned test PDF in `tests/` (§11).
2. THE containment test SHALL pass, demonstrating: an injected tool-call
   instruction is blocked at the hook and logged as a NEVER-trip; and an injected
   instruction that tries to STEER THE DRAFT is neutralized because stance fields
   are empty by construction (§4b, security.md). Both cases, not only the tool call.
3. The extractor's no-egress runtime is the second, independent containment layer:
   even if a prompt defeated the hook, the runtime cannot reach the network (§30d).

### Requirement 9: Observability, cost, and the window (§39 carry-forwards)

**User Story:** As the operator, I want this block's model spend and the real
posting window measured from our own data, so that estimates become numbers.

#### Acceptance Criteria

1. Every model call SHALL record its cost to the spend ledger (Spec 2), attributable
   by `run_id` and model id, within the ingestion/model envelope (T15).
2. After ~a week of real runs, THE System SHALL read actual monthly cost from Cost
   Explorer filtered by the four tags and replace the README's ~$4–5/mo Aurora
   ESTIMATE with the measured figure (§39 carry-forward).
3. After ~a week of real runs, THE System SHALL build the posting-time distribution
   from OUR run log's first-seen timestamps (hour + day-of-week) and propose a
   narrowed schedule window with a stated margin (§39 option 3), protecting the
   same-day special-meeting case (§35g). This replaces the current 24/7 schedule.

### Requirement 10: The demo video script — drafted in THIS block

**User Story:** As the submitter, I want the five-minute demo narratable now, so
that if it cannot be, we cut scope while cutting is still cheap.

#### Acceptance Criteria

1. THE Team SHALL draft the demo video script in this block (not at Spec 7). It
   SHALL narrate the product end to end in **under five minutes** (§9, §11).
2. IF the demo cannot be narrated in five minutes, THE Team SHALL cut scope now and
   record what was cut and why. A diffuse demo is the signal that the build is too
   diffuse.
3. The script SHALL feature the moments that show the design, not just the output:
   the receipt on a claim, the quiet week, a verifier rejection shown honestly, the
   batch-`Last-Modified` behavior the content hash absorbed (§39), and the empty
   stance fields. Captioned (§9).

## Pass gate for this block

1. Page ranges spot-checked by hand against the real PDF for a sample of items.
2. The extractor's turn cap and token cap **demonstrably fire** on an oversized
   agenda, logged and surfaced — and produce **partial items plus an honest
   "partially read" marker** (§16b eleventh state), never silence and never a
   fabricated completion.
3. The verifier **rejects a corrupted rewrite in both languages** (an added entity,
   a changed number in the Spanish), and shows original text after two failures.
4. Property tests present and passing on all six verifier checks and on extraction.
5. The model comparison is recorded with **both numbers** (verifier rejection rate,
   cost per agenda) and a chosen model with a written reason.
6. The mock renders correctly from BOTH `fixtures/sample.json` and the generated
   `fixtures/ugly.json`, including the ugly one.
7. The poisoned-PDF containment test passes (tool-call block AND draft-steering).
8. The demo video script exists and narrates in under five minutes.

## Explicitly out of scope for Spec 3

- The public site and search (Spec 4/6) — Spec 3 defines the view contract and the
  fixtures the site will consume, but does not build the site.
- The watcher and live matching (Spec 5).
- Wiring the live endpoint into the UI (Spec 6 path swap).
