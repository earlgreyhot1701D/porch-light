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
  "Avenida Victoria"); the check-5 hit is incidental to that rewrite's density (it
  scores 68.5 vs the 77.3 ES floor — all six ES: `[94.3, 68.5, 85.9, 86.2, 88.8,
  82.3]`). So it does not isolate a single variable.
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
