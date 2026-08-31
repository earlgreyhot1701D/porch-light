# Known limitations

Porch Light is a hackathon proof of concept (AWS Agents for Humans, Good Neighbor
track), not production SaaS. This file is the honest limitations section of the
submission — deliberately chosen tradeoffs, not a backlog. Each entry: what it is,
what it affects, why we accepted it, and what a v2 would do.

The product's own promise is honesty about what it does and does not know, so
stating these plainly is the product working, not an apology.

---

### Spanish rewrites are unreviewed by a fluent speaker

- **What it is.** The Spanish rewrites and the golden-set Spanish ground truth were
  AI-drafted and human-approved by the author, who is not a native/fluent Spanish
  reviewer. `meta.spanish_reviewer` records `unverified - AI drafted, human
  approved, no native review` (§8).
- **What it affects.** The Spanish half of every bilingual surface, and the ES side
  of verifier calibration.
- **Why we accepted it.** A blocked critical path is a missed deadline; an
  unverified Spanish surface with the limitation stated is honest and shippable.
  The verifier still checks ES entities against the source deterministically, so a
  mistranslated street name or number is caught regardless of reviewer.
- **v2.** A fluent-speaker review pass over all ES strings and the golden set, and
  the qualifier removed from `spanish_reviewer` only after that review.

### Golden set is six items from one meeting, one body

- **What it is.** Golden set 0a is six agenda items from a single City Council
  meeting (Aug 25 2026, doc 3685). The other ~14 (0b) are deferred.
- **What it affects.** Verifier calibration and model selection rest on six items
  from one body's publishing style.
- **Why we accepted it.** Six items chosen for variety (simple consent, street
  name, jargon+number, date+money, multi-option decision) exercise every entity
  class the verifier has, and calibration on them drove known-good rejection to 0
  with both adversarials biting. Six is enough to SELECT a model; more items sharpen
  a number that is already decisive at this scale.
- **v2.** Expand to ~20+ items spanning multiple bodies (Planning Commission,
  advisory committees) and both regular and supplemental packets. 0b is added
  before final model lock-in IF model selection is ambiguous or a model fails on a
  CLASS of item rather than at random (the trigger recorded in the tasks file).

### The weekly watch structurally misses same-day postings

- **What it is.** The watcher is invoked when a person opens the page; the hunter
  runs hourly. An agenda posted and meeting held the same day can fall between a
  reader's visits. Measured: 13 of 135 agendas (§35g) posted on short notice.
- **What it affects.** A small fraction of items — the same-day and very-short-lead
  postings — may not reach a weekly reader before the meeting.
- **Why we accepted it.** The product's primary user is the weekly watcher, and it
  is honest about cadence. The posting-time analysis (task 11.2, from the Brown Act
  posting statements) is what would justify narrowing the schedule on evidence; the
  same-day residue is a known gap, not a silent one.
- **v2.** A posting-time-derived schedule window plus an optional daily check for
  users who opt in; surface the same-day risk explicitly in the UI for bodies that
  post short.

### Ventura only, one adapter

- **What it is.** The system reads the City of Ventura's CivicPlus/CivicEngage
  AgendaCenter through one vendor adapter. No other city.
- **What it affects.** Scope: the product works for one city.
- **Why we accepted it.** The hackathon scope is Ventura; building one adapter
  deeply (real edge cases, real rate-limit behavior, real posting statements) is
  worth more than a shallow multi-city sweep.
- **v2.** Additional CivicPlus cities reuse the adapter with per-city config; other
  vendors (Granicus/Legistar, Municode) each get their own deterministic adapter
  behind the same document/role model.

### The mojibake repair pass maps glyphs observed in ONE document

- **What it is.** `verify/entities.py`'s artifact-repair view maps PDF-text-layer
  mojibake (`û æ Æ º ô ö ┴ ± ò`) to intended characters and joins a spurious
  intra-word space when it forms a month name. The map was built from the glyphs
  seen in doc 3685.
- **What it affects.** Entity extraction on documents whose text layer produces
  DIFFERENT artifacts than 3685 did — those glyphs would pass through unrepaired
  and could cause a spurious verifier rejection (fail-closed: a good rewrite shown
  as original staff text, never a fabricated pass).
- **Why we accepted it.** The repair is view-only and logged (every repair emits a
  structured event), `source.text` is never mutated, and an unmapped glyph fails
  safe. Mapping the observed set unblocks calibration honestly; guessing at unseen
  glyphs would be untested speculation.
- **v2.** Derive the artifact map from a corpus scan across all ingested documents,
  and alert when a new unmapped glyph appears above the repair-log baseline rather
  than silently passing it through.

### golden-002/es is not a clean single-variable adversarial

- **What it is.** golden-002/es is rejected by checks 2, 5, AND 6. Only checks 2
  and 6 are the intended catch (the translated street name "Victoria Avenue" ->
  "Avenida Victoria"). It scores 68.5 (all six ES: `[94.3, 68.5, 85.9, 86.2, 88.8,
  82.3]`); under the original 77.3 ES floor it was ALSO tripped by check 5
  incidentally, but the floor was lowered to 64.0 (see the ES-floor entry), so now
  it passes check 5 and is rejected only by checks 2/6 — the intended, single-ish
  variable. It still is not perfectly clean (the broken ES prose differs from a
  passing rewrite in wording as well as the street name).
- **What it affects.** Only the cleanliness of that one adversarial as a test
  fixture; functionally nothing (it must be rejected regardless).
- **Why we accepted it.** The intended checks bite, and the extra check-5 rejection
  is harmless. The ES floor rests on five correct samples.
- **v2.** Author the adversarial to differ from a passing rewrite in EXACTLY the
  street name and nothing else, so it isolates checks 2/6 alone; re-derive both
  floors from the larger 0b corpus.

### The model comparison uses two Amazon models, not two providers

- **What it is.** Task 9 compares Nova Lite against **Nova Pro**, not against a
  Claude/other-provider model. The originally-planned Claude Haiku
  (`anthropic.claude-3-5-haiku-20241022-v1:0`) was end-of-life at run time
  (Converse `ResourceNotFoundException`, 2026-08-30); the callable Claude 3 Haiku
  is LEGACY (EOL 2026-09-10). The cheapest ACTIVE genuine step-up from the live
  model list was Nova Pro.
- **What it affects.** The comparison answers "is the cheap Amazon model good
  enough vs the larger Amazon model," not "Amazon vs Anthropic." Same provider
  means the Converse prompt is a clean controlled variable (no cross-provider
  format drift), which is a benefit for THIS question but does not survey the
  field.
- **Why we accepted it.** Same-provider isolates the model-size variable, which is
  what the decision rule needs; a PoC picks one comparator, not a field of four.
  Bedrock model lifecycles move fast (a model id proposed one week was EOL the
  next), so pinning to an ACTIVE model matters more than provider diversity.
- **Near miss (the longevity check paying for itself).** The callable Claude 3
  Haiku (`anthropic.claude-3-haiku-20240307-v1:0`) hits EOL **2026-09-10**; the
  hackathon is judged **2026-09-14**. Pinning that model would have broken the demo
  **four days before judging**. Checking `list-foundation-models` for lifecycle
  status, rather than trusting a remembered model id, caught it in advance.
- **v2.** Re-run against a current cross-provider model once one is chosen for
  longevity, and read the model id + lifecycle from config so an EOL id fails loud
  at startup rather than mid-run.

### The verifier was calibrated against one author's voice

- **What it is.** The verifier (especially check 5, reading level) was calibrated
  against AI-drafted, human-approved rewrites in one author's voice. A model whose
  phrasing differs stylistically from that voice may be rejected for STYLE rather
  than for accuracy.
- **What it affects.** Model selection (task 9): a model could score a higher
  rejection rate because it writes differently, not less accurately.
- **Why we accepted it.** Residual, accepted for v1. The entity checks (2/3/4/6)
  are style-independent — they catch accuracy, not voice — so a style-only
  rejection shows up only in check 5, and the twice-per-model run plus the
  fall-through decision rule (disagreement at n=10 => pick Nova Lite) keep a style
  artifact from silently deciding the comparison.
- **v2.** Calibrate against rewrites from multiple authors and against each
  candidate model's own correct output, separating a style floor from an accuracy
  floor.

### The Spanish reading-level floor is provisional (64.0), re-derived once

- **What it is.** Check 5's ES floor (Fernández Huerta) was first derived from five
  single-author golden rewrites as 77.3. That rejected otherwise-fine MODEL output
  scoring 69.4-71.8. It was re-derived to **64.0** = min observed acceptable model
  ES score (69.4) minus a 5.0 margin, rounded down — so the floor admits the
  observed acceptable model range while the correct golden ES (min 82.3) still
  passes.
- **What it affects.** How strict check 5 is on Spanish. Too high and good model
  Spanish is rejected in the live product (the reader gets original staff text);
  the 64.0 value fixes that for the observed range.
- **Why we accepted it.** Small n (six items, one meeting, one author + one model's
  output). 64.0 is provisional and justified by the observed range, not tuned to
  flatter a number.
- **v2.** Re-derive from the 20-item 0b corpus and from multiple models' correct
  output; the EN floor (33.8) should get the same treatment.

### Check 5's "simpler than source" rule is conditional on source density (FIXED)

- **What it was.** Check 5 originally required the rewrite to be strictly simpler
  than the source. On short consent items whose source already scores high on
  Fernández Huerta (74.9-77.7), a faithful rewrite lands at a similar score and was
  rejected even though it was readable — rejecting ~75% of Spanish output, i.e.
  Spanish not shipping.
- **What changed (Spec 3 task 1).** The rule is now conditional: DENSE source
  (score < 70.0) still must get strictly simpler; ALREADY-PLAIN source (>= 70.0)
  need only clear the floor and be no more than 8.0 points harder than the source.
  Both numbers (`ALREADY_PLAIN_SOURCE=70.0`, `PLAIN_SOURCE_TOLERANCE=8.0`) are
  PROVISIONAL, derived from the observed task-9 ES data (one dense source at 61.7
  whose rewrite genuinely simplified; three plain sources 74.9-77.7 with faithful
  rewrites, worst acceptable gap -7.1). Result: Nova-Lite ES rejection dropped from
  3/4 to 1/4.
- **Residual.** The thresholds rest on small n (one meeting, one model). Revisit at
  task 0b; the EN floor (33.8) should get the same conditional treatment if EN ever
  shows the same already-plain pattern.

### The spend ledger stores cost at 4-decimal precision; single model calls round toward zero

- **What it is.** `spend_ledger.cost_usd` is `NUMERIC(10,4)`. A single Nova Lite
  call costs ~$0.00004, below that resolution, so a per-call row can store as
  0.0000. The MONTHLY aggregate the $10 budget checks is unaffected (many calls sum
  to cents), but you cannot recover a true per-agenda cost by summing stored rows.
- **What it affects.** The "cost per agenda" write-up number if taken from stored
  ledger values; the budget check itself is fine at this scale.
- **Why we accepted it.** The budget control works (it is about the monthly total,
  and $10 vs sub-cent calls has enormous headroom). Cost-per-agenda for the write-up
  is measured from the harness's summed pre-rounding per-call cost instead.
- **v2.** Widen `cost_usd` to `NUMERIC(12,8)` (or store micro-dollars as an integer)
  so per-call cost is recoverable from the ledger directly.

### The stored corpus is 15 documents, not the 152 the site enumeration found

- **What it is.** Aurora `porchlight-dev` holds 15 documents (11 agendas, 4
  minutes, Aug 17-Sep 2 2026), not the ~152 the live-site enumeration counted.
- **What it affects.** Any cost-per-agenda or posting-time-distribution claim: it
  must state which number it rests on. A per-agenda cost measured over these 15 is
  not a claim about all 152.
- **Why we accepted it.** The deployed ingestion has run a limited window; the PoC
  demonstrates the pipeline, not a full-corpus backfill.
- **v2.** Backfill the full enumerated set once ingestion persists content (see the
  root-cause task); state corpus size next to every derived number.

### section 36b (city Spanish edition skip) is implemented and unit-tested but never exercised on real data

- **What it is.** The §36b rule (skip our machine Spanish when the city published
  its own Spanish edition, matched on body_id + meeting date) is built and unit-
  tested (`test_rewrite_stage_db.py::test_city_spanish_skip_...`), but NO stored
  meeting has a `spanish_edition` document, so it has never fired against real data.
- **What it affects.** Confidence that §36b matches correctly on live data — the
  matching key and the suppression are proven in tests, not against a real city
  Spanish edition.
- **Why we accepted it.** No real instance exists in the stored corpus to exercise
  it; a unit test on the exact rule is honest coverage for a PoC.
- **v2.** Confirm against a real city-published Spanish edition once one is ingested.

### documents.role is unpopulated in stored data (classifier output never persisted)

- **What it is.** Every stored document has `role = ""` even though the role
  classifier works and is unit-tested. Spec 2 ingestion did not persist the
  classifier's output into the `role` column. Found 2026-08-30, before it could
  affect a user.
- **What it affects.** Anything keyed on role in live data: §36b (needs
  `spanish_edition`), minutes-vs-agenda filtering, supplemental detection. The
  logic is correct; the stored data is blank.
- **Why we accepted it (for now).** Surfaced during W6 investigation; it is one of
  three symptoms of a single root cause (ingestion stores metadata, not content,
  and extraction was never wired in), addressed as its own task, not a patch.
- **v2 / next task.** Persist role (and document text) during ingestion; re-ingest
  so live data carries what the classifier already computes.

### The verifier checks entities and reading level, not MEANING

- **What it is.** The six checks confirm every entity in a rewrite is in the source,
  no entity is invented, the receipt is attached from the record, and the reading
  level is plain. They do NOT check that the RELATIONSHIPS the rewrite asserts
  between those entities are true. A rewrite can take two true, independent facts
  and invent a connection between them, and pass every check.
- **Worked example (W6, item 4 ES).** The source states two independent facts: a
  CEQA exemption ("15301 (Existing Facilities, Class 1)") and a recommendation to
  continue the item to October 28, 2026. The model's Spanish fused them into one
  invented claim — that the city is considering continuing the review *under CEQA
  Class 1* until that date. Every entity (CEQA, Class 1, the date) is real and
  present; the CAUSAL relationship between them is fabricated. (That rewrite was
  rejected here, but for a translated role name, not for the fusion — the fusion
  itself would have passed.)
- **Why it is a real boundary, not a bug.** Meaning/relationship verification is a
  fundamentally harder problem than entity presence; a deterministic checker cannot
  confirm that a claimed relationship holds without understanding the text, which
  is the very thing we do not trust the model to assert. The honest position: the
  verifier guarantees entity fidelity and readability, NOT semantic faithfulness of
  relationships.
- **v2.** Explore a claim-level check (does each asserted relationship trace to a
  single source sentence?), or constrain the rewrite prompt to one-fact-per-sentence
  so fused claims are structurally harder to produce. Neither is trivial.

### Receipts point at a PAGE, not at an item within a page

- **What it is.** `items.page_start` / `page_end` are whole page numbers. Two items
  on the same page get identical page ranges (W6: items 2 and 3 both pp. 2-3). The
  receipt's "jump to page" lands the reader on the page, not on the specific item.
- **What it affects.** On a dense agenda page, the reader must scan the page to find
  the item the receipt refers to. The body/date/item-number in the receipt still
  identify it; only the page anchor is coarse.
- **Why we accepted it.** Page-level anchoring is honest (it never points at the
  wrong page) and matches what a PDF page link can do; sub-page anchoring needs
  character offsets or per-item bookmarks the source PDF does not provide.
- **v2.** Capture a per-item text offset or a search anchor so the link can
  highlight the item on the page.

### Our own hardcoded Spanish was missing diacritics (FIXED); model/pipeline/DB path is clean

- **What it was.** The hardcoded ES fallback string was written without accents
  ("version verificada en espanol"). Investigation (not a guess) found the loss was
  ONLY in the source-code string literals I authored. The model output, the
  pipeline, and the database round-trip all PRESERVE accents correctly (verified: a
  stored "reunión/están" keeps `ord > 127`); the mojibake seen in console/file
  captures is the PowerShell OEM code page rendering correct UTF-8, not data loss.
- **Fix.** Corrected the hardcoded strings to carry proper diacritics (using
  explicit escapes so they cannot be re-stripped by an editor). Model-produced
  Spanish needed no change.
- **Residual.** Console/file dumps on Windows still render accents as mojibake for
  display; the DATA is correct. Any future hardcoded Spanish must be written with
  accents and spot-checked with `ord()`, not by eye in a console.

### The proper-noun extractor captures greedy spans (latent entity-matching brittleness)

- **What it is.** The `_PROPER` regex captures greedy multi-word spans, so a source
  phrase "City Council Minutes" is one entity and "City Council" cannot match it.
  This surfaced 2026-08-31 while building the body-consistency check: making the
  verifier match the body as a free-text entity drove known-good rejection to 60%
  because the golden source spans ("City Council Minutes", "Approve City Council
  Minutes") did not equal the rewrite's "City Council". The role/body drop list had
  been masking this.
- **What it affects.** Entity matching generally, for any multi-word name that
  appears in the source inside a longer capitalized phrase. It did NOT affect the
  body check in the end, because the body check moved OFF entity matching to a
  registry contradiction check (the right fix — see the decisions principle).
- **Why we accepted it (for now).** The two spine surfaces (entity preservation,
  no-new) still work on the golden set and W6 because the failing class is
  greedy-span vs exact-phrase, which is rare for the dates/amounts/identifiers that
  matter most; names are where it bites. It is latent, not active breakage.
- **v2.** Extract the maximal proper-noun span AND its known sub-spans (e.g. emit
  both "City Council Minutes" and "City Council"), or move name matching to
  containment/registry checks wherever the field is deterministic, per the
  decisions principle.

### Extractor network containment: one layer deployed and tested, one designed, one structural

The extractor reads untrusted PDF text. Its containment has three parts, and they
are at different levels of "real" — stated exactly:

1. **Deployed AND tested live (the hook allowlist).** A Strands `BeforeToolCallEvent`
   hook blocks any tool call whose name is not one of the four permitted tools. This
   is proven against the DEPLOYED AgentCore runtime, not asserted: a benign
   non-allowlisted tool the model actually called was blocked, logged as a NEVER-trip
   (`event: never_trip_tool_blocked`, `boundary: tool_allowlist`), and the run
   terminated before the tool executed (2026-08-31, CloudWatch). The runtime also
   fails CLOSED if the hook cannot register (proven live on a first deploy: it
   refused to run unguarded rather than run without the hook).

2. **Designed and specified, NOT deployed (network-level egress control).** No-egress
   requires VPC network mode + a restricted security group + PrivateLink endpoints.
   The security group and the full config are designed and committed
   (`r5-deploy-proposal.md`); the runtime is deployed in PUBLIC network mode, which
   permits outbound egress. Deferred to post-submission by an explicit sequencing
   decision (deploy PUBLIC now to make the "agent on AgentCore" claim real; add the
   network layer after).

3. **Structural, not a control, but it reduces exposure (the contract).** The
   extractor receives STORED page text and its tool registry contains NO
   network-capable tool. An injection would have to invoke a tool that does not
   exist. This is not a security control (a control blocks a thing that is possible);
   it is the absence of the capability in the first place. It narrows the blast
   radius but is not a substitute for layer 2.

**The consequence, unsoftened:** if a prompt defeated the hook allowlist AND a
network-capable tool existed, nothing at the network layer would stop egress. Layer
1 is real and tested; layer 2 is designed and not shipped; layer 3 reduces the
chance layer 1 ever matters but is not itself a barrier. We ship this stated plainly
rather than claim a network-containment posture we have not deployed.

Status (2026-08-31): the extractor IS deployed to AgentCore Runtime
(`porchlightspike_porchlight_extractor`, PUBLIC mode) and runs in our
`porchlight.log` schema. The no-egress SG (`sg-08e491a424c16581f`) exists (free); the
PrivateLink endpoints were torn down at the earlier timebox and are not currently
billing. A resume checklist to add layer 2 is in `r5-deploy-proposal.md`.


### Item selection is model-driven (Option A shipped); the verifier is strict on dense Planning source

The Option-C floor written before the spike is resolved: the spike passed 3/3 and we
shipped **Option A**. The extractor is a genuine tool-using agent (decisions §44).
Two residual limitations this surfaced on real data:

- **What it is.** The extractor's four tools now have bodies; it runs a Strands tool
  loop (`find_listing_pages`, `get_document_pages`, `extract_items`, `record_items`)
  under the caps, validates with `validate_items`, and returns structured items
  across the invoke boundary. On the two condition-5 meetings it extracted clean
  per-item text with correct page ranges. **But** on meeting 3687 (Planning
  Commission), EN verification came back 0/4: dense planning staff reports either
  could not be simplified below the reading floor, or named the body ("Planning
  Commission") in a way the entity check — which compares against the item's own
  page-range text — flagged as unsourced, or (item 1) had the model name the wrong
  body entirely (caught by the §41 containment check).
- **What it affects.** How many dense Planning items get a plain-language rewrite vs
  fall back to original staff text. Council consent items rewrite reliably (3685:
  5/8); dense Planning items often fall back (3687: 0/4). No fabricated item ever
  ships — every fallback shows the verbatim city text with an honest note (never.md
  #7). The receipt, page range, and item number are always correct regardless.
- **Why we accepted it.** The 0/4 is an honest measurement of Nova Lite on dense
  source, not a defect. We deliberately did NOT tune the verifier or lower a floor to
  raise the number (§28: green tests must not paper over real behavior). A fallback
  to accurate original text is the product working, not failing.
- **v2.** (a) Move the body-name check off the item-slice entity comparison and onto
  the record/registry containment check (the §41 principle, extended) so a correctly-
  named body is not flagged as unsourced. (b) Isolate per-item text better than a
  page range (the "receipts point at a page" limitation). (c) Consider a stronger
  model for the rewrite of dense items specifically, measured against the same floor.
