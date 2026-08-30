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

### Verifier check 5 (reading level) is coupled per-item, and one adversarial trips it incidentally

- **What it is.** The reading-level floors (EN 33.8 Flesch, ES 77.3 Fernández
  Huerta) are DERIVED from the six-item 0a set. The adversarial golden-002/es
  scores 68.5 (all six ES: `[94.3, 68.5, 85.9, 86.2, 88.8, 82.3]`), so it is
  rejected by check 5 as well as by checks 2/6 (the intended street-name catch) —
  the check-5 rejection is incidental to how that broken rewrite happens to be
  phrased, not check 5 doing the street name's job.
- **What it affects.** Nothing functionally today (the adversarial must be rejected
  regardless). It means the ES floor rests on five correct samples.
- **Why we accepted it.** The floor is sound at this scale (all ten correct rewrites
  pass, adversarial clears it by 8.8 points); the incidental multi-check rejection
  of an adversarial is harmless.
- **v2.** Re-derive both floors from the larger 0b corpus; the ES rewrite-vs-source
  gap (~15.6) is much tighter than EN (~33.7) and a 20-sample floor may move.
