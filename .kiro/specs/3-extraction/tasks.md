# Implementation Plan: Spec 3 — Extraction, Rewrite, Verifier

## Overview

Turn a stored agenda into verified, bilingual, receipt-bearing items and a
stance-free draft; calibrate the verifier against human ground truth; choose the
production model on measured evidence; define the view contract; draft the demo
script. Approved requirements + design govern.

**Critical-path artifact: the golden set ([HUMAN], owner Shara), split to unblock
early.** It is calibration ground truth, the model-comparison sample, and the
adversarial-case source. **Task 0a** (six varied items) gates calibration (task 8);
**task 0b** (~14 more, where sample size matters) gates model selection (task 9).
Neither gates the build of the extractor, normalizer, checks, deadline renderer,
draft scaffold, or contract — those are sequenced first so the human task never
blocks the agent's first waves.

Rigor budget (style.md): **working rigor on real agendas + property tests on the
two spine surfaces (the six verifier checks, the entity normalizer) and on
extractor page-range/entity output.** Model output tested against captured real
docs + the golden set, never a description (testing.md).

Tags: [HUMAN] Shara owns. [PERMANENT] ships. [TEST]. [INFRA-PROPOSE] billable/external.

## Tasks

- [ ] 0a. [HUMAN] Golden set — the calibration six (owner: Shara)
  - [ ] 0a.1 Fill `tests/golden/golden_set.json` with SIX items chosen for variety
    - One dense ordinance, one simple consent item, one with a dollar amount, one with a street address, one with a date/deadline, one genuinely hard to summarize. Each: verbatim source page-range text (hand-copied), hand-written correct EN + ES rewrites. Include a couple `is_adversarial: true` broken rewrites + reason.
    - Six is enough to catch an over-strict check; unblocks calibration tonight instead of in 3 days.
    - **§8 fallback (explicit, so an unfound reviewer cannot silently block):** if no fluent Spanish reviewer is available when 0a is due, Shara writes the Spanish, `meta.spanish_reviewer` records "unverified — author Spanish, no native review", and the README states the Spanish surface is unverified per §8. Calibration proceeds on that basis with the limitation recorded. An unverified Spanish golden set is a stated limitation; a blocked critical path is a missed deadline.
    - Gates: task 8 (calibration). Does NOT gate tasks 1–7.
    - _Requirements: §11 golden set; R3.5_

- [ ] 0b. [HUMAN] Golden set — the remaining ~14 (owner: Shara)
  - [ ] 0b.1 Add ~14 more real items in the same format, before the model comparison
    - Sample size matters for the rejection-rate number that picks the model. Same §8 fallback applies.
    - Gates: task 9 (model selection). Does NOT gate calibration (task 8 runs on 0a).
    - _Requirements: §11 golden set; R5.2_

- [ ] 1. Entity normalizer + entities (spine surface #1) [PERMANENT]
  - [ ] 1.1 `verify/entities.py` (extract candidate entities) + `verify/normalize.py` (canonicalize dates/numbers, leave names raw) — pure, no model, no I/O
    - Rule per design table: NORMALIZE dates→ISO8601, numbers/currency/percent→numeric+unit; COMPARE RAW proper nouns/person/street/body names. Handle US and es number formats.
    - _Requirements: 3a.1, 3a.2, 3a.4_
  - [ ] 1.2 Property tests: normalizer both-ways [TEST]
    - **Property: EN/ES equivalent dates+numbers normalize EQUAL; a genuinely different value does NOT (no over-normalization); a translated proper noun does NOT match (raw).**
    - Tag: `# Feature: 3-extraction, Property 1: entity normalizer`
    - _Requirements: 3a.3_

- [ ] 2. Reading level, per language [PERMANENT]
  - [ ] 2.1 `verify/reading.py` using pinned `textstat`: Flesch (en) + Fernández Huerta (es)
    - Thresholds left as parameters; DERIVED from the golden set in task 8 (not guessed here).
    - _Requirements: 3b.1, 3b.2 (3b.3 fallback not needed — textstat has Spanish)_

- [ ] 3. The six checks + verifier orchestration (spine surface #2) [PERMANENT]
  - [ ] 3.1 `verify/checks.py` (six pure checks) + `verify/verifier.py` (run all six, one retry w/ reason, else original-text fallback + count)
    - Checks 2/3/6 compare on normalized entities (task 1); check 5 uses task 2; check 4 asserts id/page-range/deadline/body from the record.
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ] 3.2 Property tests: each of the six checks [TEST]
    - **Property: each check REJECTS its adversarial case (added entity, dropped date, altered amount, unsimplified copy, ES changed number, ES translated street name) and PASSES a known-good case.**
    - Tag: `# Feature: 3-extraction, Property 2: verifier checks`
    - _Requirements: 3.5_

- [ ] 4. Extractor agent (no-egress AgentCore runtime) [PERMANENT]
  - [ ] 4.1 `agents/extractor/{tools,agent,entrypoint}.py`: find_listing_pages → get_document_pages(range) → extract_items → record_items; cap 6 + token cap; tools allowlisted at hook; item#/page-range copied from source, reject if absent
    - Partial-cap-fire (R1.7): keep extracted items, mark document `partially_read` + reason + source link.
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7_
  - [ ] 4.2 Property test: extractor never emits an item#/page-range absent from source [TEST]
    - Tag: `# Feature: 3-extraction, Property 3: extraction fidelity`
    - _Requirements: 1.5_

- [ ] 5. Deadline renderer [PERMANENT]
  - [ ] 5.1 `deadline/render.py`: city-local, always labeled, relative phrasing vs city time, DST-boundary test. Copied from source or not shown.
    - _Requirements: 7.1, 7.2_

- [ ] 6. Draft scaffold (structure, never stance) [PERMANENT]
  - [ ] 6.1 `draft/scaffold.py`: facts + receipt + logistics; stance fields empty by construction; every factual element passes the verifier; no send capability anywhere
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 7. View contract + fixtures [PERMANENT]
  - [ ] 7.1 `web/contract.py` (the view JSON the site consumes) + `fixtures/build_fixtures.py` (generate sample.json + ugly.json FROM real data; 95th-pct length computed; synthetic:true where no real instance)
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 8. Verifier calibration (GATED on task 0a — the six) [TEST]
  - [ ] 8.1 Run all six checks against the golden set's hand-written correct rewrites
    - Any check that REJECTS a known-good rewrite is WRONG → fix/narrow it, record what changed and why. Derive check-5 thresholds (en + es) from the hand-written rewrites' reading scores vs sources; record both numbers. Gate: rejection rate on known-good rewrites = 0 before task 9.
    - _Requirements: 3.5, 3b, R5 (precondition)_

- [ ] 9. The rewrite chain + model selection (GATED on task 8 AND task 0b) [PERMANENT] [INFRA-PROPOSE for live model calls]
  - [ ] 9.1 `rewrite/chain.py` + `rewrite/model.py`: source→EN→verify→ES→verify-against-source; temp ~0, no tools, no loop; Strands-vs-Converse decided + recorded; city-Spanish-edition skip on body_id+date (§36b)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [ ] 9.2 Model comparison over the golden set: Nova Lite vs one stronger model; record verifier rejection rate + cost/agenda for each; pick + write the reason
    - Model id from config, in every log event; no silent fallback. Live model calls — PROPOSE before running the paid comparison.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 10. Prompt-injection containment [TEST]
  - [ ] 10.1 Poisoned PDF in `tests/`; containment test: tool-call blocked at hook (NEVER-trip) AND draft-steering neutralized (stance empty by construction); no-egress runtime is the second layer
    - _Requirements: 8.1, 8.2, 8.3_

- [ ] 11. Observability / cost / window (§39 carry-forwards) [PERMANENT]
  - [ ] 11.1 Model calls record cost to the ledger by run_id + model id (T15 envelope)
    - _Requirements: 9.1_
  - [ ] 11.2 After ~a week of real runs: Cost Explorer by four tags → replace README Aurora estimate; posting-time distribution from our run log → propose narrowed schedule window w/ margin (§39, §35g)
    - _Requirements: 9.2, 9.3_

- [ ] 12. Demo video script (drafted THIS block) [HUMAN-ish, drafted with Shara]
  - [ ] 12.1 Draft the < 5-minute narration; if it can't be narrated in 5 min, cut scope now + record what/why. Feature: receipt, quiet week, honest verifier rejection, batch-Last-Modified/content-hash moment (§39), empty stance fields. Captioned.
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 13. Final checkpoint
  - All property + working-rigor tests pass. Pass gates 1–8 met (page ranges hand-checked; caps fire → partial+marker; verifier rejects corrupted both-lang; six-check property tests; model comparison with both numbers + chosen model; mock renders from both fixtures; poisoned-PDF containment; video script narrates < 5 min). Verifier calibrated (known-good rejection rate = 0) before model selection. Working tree clean; account ID clean.
  - _Requirements: pass gate 1–8_

## Notes

- The rewrite lives in `rewrite/`, not `agents/`: no tools, no loop, temp ~0 (model-authority as a directory).
- Property tests: `# Feature: 3-extraction, Property {N}: {title}`.
- The verifier is calibrated (task 8) BEFORE it judges models (task 9): otherwise the rejection rate measures our bug, not the model.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0a.1", "0b.1"], "note": "[HUMAN] Shara — parallel with waves 1-4. 0a (six) gates task 8; 0b (~14 more) gates task 9. Neither gates tasks 1-7." },
    { "id": 1, "tasks": ["1.1", "2.1", "5.1"] },
    { "id": 2, "tasks": ["1.2", "3.1", "6.1", "7.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "10.1"] },
    { "id": 4, "tasks": ["4.2", "11.1"] },
    { "id": 5, "tasks": ["8.1"], "note": "GATED on task 0a (the six)" },
    { "id": 6, "tasks": ["9.1", "9.2"], "note": "GATED on task 8 AND task 0b; 9.2 is INFRA-PROPOSE (paid model calls)" },
    { "id": 7, "tasks": ["11.2", "12.1"] },
    { "id": 8, "tasks": ["13"] }
  ]
}
```
