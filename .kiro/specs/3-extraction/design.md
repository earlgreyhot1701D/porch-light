# Design Document — Spec 3: Extraction, Rewrite, and the Verifier

## Scope

Turn a stored agenda into verified, bilingual, receipt-bearing items and a
stance-free draft scaffold; choose the production model on measured evidence;
define the view contract and generate fixtures; draft the demo script. References
the approved requirements and §2/§3/§4/§4b/§11/§21/§25/§27/§30d/§35a/§36b/§38/§39.
Rigor budget and pass gate are in requirements.md and not restated. The verifier
and the entity normalizer are the two spine surfaces; both get property tests on
every check.

## Module layout (structure.md: one file, one responsibility)

```
agents/
  extractor/
    agent.py          # the AgentCore Strands agent: cap 6, no egress, tools below
    tools.py          # find_listing_pages, get_document_pages(range), extract_items, record_items
    entrypoint.py     # @app.entrypoint for the extractor's OWN runtime (no egress)
verify/
  normalize.py        # R3a: entity normalizer (dates/numbers → canonical; names raw). PURE.
  entities.py         # extract entities from text (numbers, dates, currency, %, proper nouns)
  checks.py           # the six checks (schema, entity-preserve, no-new, containment, reading, both-lang). PURE.
  verifier.py         # orchestrates the six checks; one retry with reason; else original-text fallback
  reading.py          # R3b: per-language reading level (textstat: FK en, Fernández Huerta es)
rewrite/
  chain.py            # source → EN → verify → ES → verify-against-source (§21a). temp ~0, no tools, no loop.
  model.py            # model id from config; Strands-vs-Converse decision recorded here
draft/
  scaffold.py         # R4: facts + receipt + logistics; stance fields empty by construction
deadline/
  render.py           # R7: city-local, always labeled, relative phrasing, DST-tested
web/
  contract.py         # R6: the view contract (the JSON the site consumes)
fixtures/
  build_fixtures.py   # R6: generate sample.json + ugly.json FROM real ingested data
```

The extractor lives in `agents/` (a genuine agent, §38). The rewrite is NOT an
agent (temp ~0, no tools, no loop) so it lives in `rewrite/`, not `agents/`. The
verifier, normalizer, and checks are pure code in `verify/` — the model never
touches them.

## Containment is a CONTRACT property, not only a network policy (R2 consequence, §41-adjacent)

After R2 (ingestion persists per-page document text), the extractor receives its
input as **stored text**, never a URL and never a fetchable document id it would
have to resolve. The pipeline reads `document_pages` and passes the page text into
the invoke; the extractor's contract accepts no argument that requires the network.

This makes containment a property of the extractor's CONTRACT, not merely a
configuration on its runtime. The no-egress networkMode and the tool allowlist are
the enforcement layers, but the deeper fact is that **nothing in the extractor's
job needs the network in the first place** — it reads text it was handed and writes
items. A runtime with egress accidentally left on would still have nothing in the
extractor's contract that wants to use it. Two independent enforcement layers
(networkMode + hook) sit on top of a contract that has no network need at all. That
is the strongest form of the §19c/§30d/R8.3 guarantee: not "we blocked the network"
but "the work never asked for it."

## The extractor (R1) — an agent, in its own no-egress runtime

- **Separate AgentCore runtime from the hunter.** The hunter is a Lambda with
  egress (§38); the extractor is an AgentCore runtime with **networkMode giving no
  egress** (§30d). Two runtimes, not two roles on one — networkMode is per-runtime.
  Egress-none at the runtime AND tool-allowlist at the Strands hook = two
  independent containment layers (§security, R8.3).
- **Tools** (allowlisted at the hook): `find_listing_pages(document_id)` (first,
  always), `get_document_pages(document_id, range)` (only this document, hard
  page-count cap), `extract_items(page_range)` (schema-constrained), `record_items`
  (its own table only — cannot write documents or drafts). **No fetch, no shell,
  no network.**
- **Caps:** turn cap 6, hard token cap. Both fire on an oversized agenda and are
  logged + surfaced. On a cap fire mid-document (R1.7): the items already recorded
  stand, the document row is marked `partially_read` with the reason + source link,
  and that partial marker renders alongside the real items — never partial-as-complete.
- **Item numbers and page ranges are copied from source**; output containing any
  not present in the source is rejected before storage (the extractor's own
  invisible-failure surface → property tests).
- **Input is untrusted** (§9): an injected instruction in packet text is data, not
  a command; a blocked tool call logs a NEVER-trip.

## The rewrite chain (R2, §21a) — code-directed, not an agent

```
source page-range text (from extraction record)
  → EN rewrite   (model, temp ~0, structured output, no tools)
  → verify EN against SOURCE (six checks)         ── fail? one retry w/ reason; fail twice? show original staff text
  → ES translate of the VERIFIED EN               (model, temp ~0)
  → verify ES against the ORIGINAL SOURCE (six checks, normalized entities)
```

- Both languages verify against the **original source**, never EN-vs-ES (§21d). The
  one allowed chain hop is ES-from-verified-EN, and it is still checked against source.
- **Strands vs direct Converse:** decided at block start on the evidence (§27). The
  rewrite has no tools and no loop, which argues for direct Converse (less
  machinery); recorded in `rewrite/model.py` with the reason. Not assumed.
- Dates/deadlines/item numbers/page ranges/body/URL are **attached from the
  extraction record**, never model-emitted (containment, check 4).
- **City-published Spanish (§36b):** if a meeting has a city Spanish edition,
  matched on **body_id + meeting date**, the ES chain does NOT run for it; the
  receipt points at the city's Spanish document. Date-only matching is banned
  (two bodies same day would cross-link).

## The entity normalizer (R3a) — the fix that keeps Spanish alive

The decision, stated: **normalize the classes that legitimately change surface
form across languages; compare raw the classes that must never be translated.**

| Entity class | Treatment | Why |
| --- | --- | --- |
| Dates | NORMALIZE → ISO 8601 | `February 10, 2026` = `10 de febrero de 2026` = `2026-02-10` |
| Numbers, currency, percent | NORMALIZE → numeric value + unit/flag | `1.2 million` = `1.2 millones` = `1,200,000` → `1200000`; `$1,200,000` carries a currency flag; `5%` → `5·pct` |
| Proper nouns, person names | COMPARE RAW | a name that changed in translation is a real failure |
| Street names, body names | COMPARE RAW | "Main Street" must not become "Calle Principal" in a receipt-bearing line |

- `verify/normalize.py` is pure, no model, no I/O. `verify/entities.py` extracts
  candidate entities; the normalizer canonicalizes the two normalize-classes and
  leaves the raw-classes untouched.
- **Property tests (invisible-failure both ways):** equivalent date/number forms in
  EN and ES normalize equal; a genuinely different number does NOT normalize equal
  (no over-normalization masking drift); a translated proper noun does NOT match
  (stays raw). Adversarial cases from the golden set.
- Risk acknowledged: locale number formats (`1.234,56` vs `1,234.56`) — the
  normalizer handles both the US and the es-formatting conventions; the test set
  includes both.

## Reading level, per language (R3b) — `textstat`

- Library: **`textstat`** (pinned), which implements Flesch-Kincaid/Flesch Reading
  Ease for English and **Fernández Huerta for Spanish** — one pinnable library
  covers both, so the fallback proxy in R3b.3 is NOT needed. Recorded.
- English: Flesch Reading Ease, threshold TBD-at-build (target ~"plain"); Spanish:
  Fernández Huerta with its own threshold. Never the English number on Spanish text.
- Check 5 passes only if the rewrite is simpler than the source by the
  language-appropriate metric.

## The six-check verifier (R3) — pure, the spine

`verifier.verify(rewrite, source_record, lang) → Pass | Fail(reason)`. Each check
in `checks.py` is a pure function with its **own property tests** (R3.5):

1. schema — structured output present.
2. entity preservation — every normalized output entity ∈ source entities.
3. no new entities — every normalized output entity has a source origin.
4. containment — id/page-range/deadline/body taken from the record, asserted equal.
5. reading level — per-language metric below the threshold.
6. both languages — check 2/3 on the ES output against the source (normalized).

Retry policy (§4, model-authority): fail once → one retry with the failure reason
attached (code decides, not a loop); fail twice → mark item unrewritten, show
original staff text with a note, count the rejection. **The model never grades
itself.** Rejection counts feed §27 model selection.

**Per-language fallback (pipeline decision, never-fail-open).** The two languages
fall back independently, because one can verify while the other does not:

- **English fails twice →** show the original English staff text for that item with
  a plain note that a verified plain-English summary was not produced. Never the
  unverified rewrite.
- **Spanish fails twice →** emit the **verified English rewrite** for that item and
  state plainly that a verified Spanish version was not produced for it. Porch Light
  **never emits an unverified rewrite** (EN or ES) and **never silently drops the
  item** — the item is always shown, with an honest statement of what could be
  verified. This is the never-fail-open rule (never.md #7): a degraded dependency
  produces an honest, labeled partial result, not a fabricated or silently-dropped
  one. The model is Nova Lite for both the attempt and the retry (no silent
  provider fallback, never.md #7).

Adversarial test cases (R3.5): added entity, dropped date, altered dollar amount,
unsimplified copy, ES rewrite with a changed number, ES rewrite with a translated
street name. Each must be REJECTED. Plus real golden-set rewrites that must PASS.

## The draft scaffold (R4) — structure, never stance

- `draft/scaffold.py` assembles: item + what it is, receipt (body/date/item#/page
  range/PDF link), logistics, how/where to submit, deadline (city local). Then
  **labeled empty fields**: your position / why this matters to you / what you are
  asking for.
- Stance fields are empty **by construction** — the code never has a stance value
  to fill, so injected text has nothing to steer (§4b, never.md #5).
- Every factual element passes the verifier. **No send capability** exists anywhere
  (never.md #4).

## Verifier calibration (BEFORE model selection) — the verifier is under test first

The model comparison (R5) picks a model on verifier rejection rate. If a check is
stricter than a genuinely-good plain-language rewrite can satisfy, that number
measures the VERIFIER's bug, not the model. So the verifier is calibrated against
human ground truth first, and only then used to judge models.

- **Ground truth:** the golden set includes, per item, a HAND-WRITTEN correct
  plain-English rewrite and a hand-written correct Spanish one — written and judged
  correct by a human (Spanish via the §8 fluent reviewer).
- **Calibration run:** all six checks run against those hand-written rewrites. **Any
  check that rejects a hand-written correct rewrite is WRONG** — the human rewrite
  is ground truth, the verifier is the thing under test. Fix or narrow the check,
  record what changed and why.
  - Concrete risk, check 3 (no new entities): a good rewrite may say "the property
    on Main Street" where the source page range only had "APN 073-0-123-456".
    That is what a resident needs, not a new entity in the forbidden sense — the
    calibration will surface whether check 3 is too strict about
    reference-resolution vs. genuine invention, and the fix is recorded.
- **Check 5 thresholds are DERIVED, not guessed:** compute the reading scores
  (Flesch en, Fernández Huerta es) of the hand-written rewrites vs. their sources;
  the threshold is set from that gap. Record both numbers.
- **Gate:** the model comparison runs ONLY after the verifier passes every
  hand-written correct rewrite (rejection rate on known-good rewrites = 0). Record
  which checks were adjusted, the derived thresholds, and that zero.

## Model selection (R5, §27)

- Run Nova Lite vs one stronger model (e.g. a Claude model) over the **golden set
  (~20 hand-checked items)** — the countable, reproducible sample.
- Record per model: **verifier rejection rate** (how often the six checks reject,
  both languages) and **cost per agenda** (from the spend ledger, by model id).
- Pick the cheapest model that clears the quality bar; write down the choice and
  both numbers (README + a builder.aws.com post, §11). Model id from config, in
  every log event (§27). No silent fallback (§20f).

## The golden set — format (the [HUMAN] ground-truth artifact)

One file, `tests/golden/golden_set.json`, ~20 entries built in two parts: **0a** =
the first six varied items (dense ordinance, simple consent, dollar amount, street
address, date/deadline, hard-to-summarize) which gate calibration; **0b** = the
remaining ~14 which gate model selection. It is calibration ground
truth, the model-comparison sample, and the source of adversarial cases, so its
shape is chosen to make the tests clean: each entry carries the real source text,
the expected deterministic extraction, and the hand-written correct rewrites.

```jsonc
{
  "meta": {
    "owner": "shara",
    "verified_date": "2026-09-0X",
    "spanish_reviewer": "<name or 'UNVERIFIED — §8'>",
    "notes": "~20 items hand-read against the real PDFs"
  },
  "items": [
    {
      "id": "golden-001",
      "source": {
        "body_id": "city_council",
        "meeting_date": "2026-02-10",
        "document_url": "https://www.cityofventura.ca.gov/AgendaCenter/ViewFile/Agenda/_02102026-3569",
        "item_number": "7",              // copied from the PDF, by hand
        "page_range": [4, 5],            // copied from the PDF, by hand
        "text": "<verbatim staff text for this item's page range>"
      },
      "expected_entities": {             // what the normalizer/checks should find in source
        "dates": ["2026-02-10"],
        "numbers": [1200000],
        "raw_names": ["Main Street", "Planning Commission"]
      },
      "rewrite_en": "<hand-written correct plain-English rewrite>",
      "rewrite_es": "<hand-written correct Spanish rewrite>",
      "is_adversarial": false           // true entries carry a deliberately-broken rewrite + why
    }
  ]
}
```

- **Human fills:** `source.item_number`, `source.page_range`, `source.text`,
  `rewrite_en`, `rewrite_es`, and the meta. The `expected_entities` can be
  hand-filled or machine-proposed then human-checked.
- **A few entries are adversarial** (`is_adversarial: true`) carrying a
  deliberately-broken rewrite (added entity, changed number, translated street
  name, unsimplified copy) plus the reason — these are the "must REJECT" cases.
- Tests load this one file: calibration asserts every non-adversarial `rewrite_en`
  / `rewrite_es` PASSES all six checks; adversarial entries must be REJECTED;
  check-5 thresholds are derived from the non-adversarial reading-score gaps.

## Contract-first fixtures (R6, §25)

- `web/contract.py` defines the view contract (the JSON the site consumes): item
  content, both-language summaries, receipt, deadline (rendered), status flags
  (rewritten / original-text / unreadable / partially-read / missing-ES).
- `fixtures/build_fixtures.py` generates `fixtures/sample.json` and hostile
  `fixtures/ugly.json` **from real ingested data** (testing.md #3): longest real
  body name, an unrewritten item, an unreadable doc, a missing ES edition, a null
  deadline, no-clean-page-range item, 95th-percentile summary length (computed,
  recorded in the header). `synthetic: true` marks any category with no real instance.
- The mock reads these; Spec 6 is then a path swap (fixture → live endpoint).

## Deadline rendering (R7)

- `deadline/render.py`: store timestamptz, render America/Los_Angeles always
  labeled, relative phrasing computed against city time, explicit DST-boundary
  test. Copied from source or not shown (never.md #1). Built here because fixtures
  need real rendered values (§25d).

## Prompt-injection containment (R8, §11)

- A poisoned PDF in `tests/`: (a) an injected tool-call instruction blocked at the
  hook, logged NEVER-trip; (b) an injected draft-steering instruction neutralized
  because stance fields are empty by construction. Both tested. The no-egress
  runtime is the independent second layer.

## Observability / cost / window (R9, §39)

- Every model call records cost to the spend ledger by run_id + model id, inside
  the T15 model envelope.
- After ~a week of real runs: read Cost Explorer by the four tags → replace the
  README Aurora estimate with the measured number; build the posting-time
  distribution from our run log's first-seen timestamps → propose the narrowed
  schedule window with margin (§39), protecting same-day meetings (§35g).

## Demo video script (R10) — drafted here

- Draft the < 5-minute narration this block. If it cannot be narrated in five
  minutes, cut scope now and record what/why. Feature: a receipt on a claim, the
  quiet week, an honest verifier rejection, the batch-`Last-Modified`/content-hash
  moment (§39), the empty stance fields. Captioned.

## Testing (rigor budget)

**Property tests (invisible-failure surfaces):**
- `verify/normalize.py` — normalize-equal across EN/ES for dates/numbers; not-equal
  for genuinely different values; raw for names.
- each of the six `verify/checks.py` — rejects its adversarial case, passes golden.
- extractor entity/page-range extraction — never emits an item number or page range
  absent from source.

**Working-rigor (real agendas + golden set):**
- Page ranges spot-checked by hand for a sample.
- Caps fire on an oversized agenda → partial items + partial marker.
- Verifier rejects a corrupted rewrite in both languages; shows original after two fails.
- Model comparison recorded with both numbers.
- Mock renders from sample.json AND ugly.json.
- Poisoned-PDF containment (tool-call block AND draft-steering).

Model output is tested against captured real documents and the golden set, never a
description of what the model should return (testing.md).

## Explicitly out of scope

The public site and search (Spec 4/6; Spec 3 defines the contract + fixtures), the
watcher/live matching (Spec 5), wiring the live endpoint (Spec 6 path swap).
