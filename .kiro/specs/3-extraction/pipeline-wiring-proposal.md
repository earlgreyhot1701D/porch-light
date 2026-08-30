# Spec 3 — rewrite-chain pipeline wiring PROPOSAL (propose only, not built)

Status: **PROPOSE ONLY.** Awaiting approval before any build. Model is fixed
(Nova Lite, from config). The verifier is calibrated (known-good rejection 0,
adversarials bite). Check 5 is conditional on source density. This proposal wires
the rewrite chain into the pipeline and ends with one live end-to-end run against
a real Ventura agenda.

## What already exists (do not rebuild)

- `rewrite/model.py` — Nova Lite via Converse, model id from config, cost per call.
- `rewrite/chain.py` — controlled EN/ES prompts + message builders.
- `verify/verifier.py` — `verify()` and `verify_with_retry(rewrite_fn, ...)`.
- `agents/extractor/*` — extractor agent, source-fidelity guard, caps, partial-read.
- `ledger.record_model_spend` — run_id + model id cost recording.
- Aurora schema: `documents`, `items` (item_number, page_start/end), `spend_ledger`.

## Proposed tasks (each small, each verifiable)

- **W1. Compose the rewrite_fn (no new model logic).** A thin adapter that binds
  `chain.REWRITE_PROMPT_EN/ES` + `model.invoke` (Nova Lite from config) into the
  `rewrite_fn` signature `verify_with_retry` expects. Pure wiring; unit-tested with
  a stub client, no live call.
  - _Verify:_ unit test with a fake Converse client returns a Rewrite; retry path
    exercised with a stubbed first-fail.

- **W2. Per-language fallback outcome (the never-fail-open decision, design.md).**
  Implement the recorded rule as code: EN fails twice → original English staff text
  + note; ES fails twice → verified English + "verified Spanish not produced for
  this item"; never emit unverified, never drop. Returns a structured per-item
  result carrying which languages verified.
  - _Verify:_ unit tests for all four states (EN ok/ES ok, EN ok/ES fail, EN fail,
    both fail) assert the item is always present and never carries an unverified
    rewrite. Property: no code path emits a rewrite the verifier rejected.

- **W3. Persist verified items.** Write accepted rewrites + the per-item verify
  outcome to storage (the `items` table + a small rewrite/verification record).
  Item number / page range / body / deadline attached from the extraction record
  (containment), never from model output.
  - _Verify:_ DB-backed test (skips without DATABASE_URL): an item round-trips;
    receipt fields come from the record; a twice-failed ES item stores EN + the
    honest ES-absent marker.

- **W4. Cost + observability on the real path.** Every model call records cost by
  run_id + model id (existing ledger); model id in every structured log event;
  rejection counts surfaced. Sub-budget check before the rewrite stage runs.
  - _Verify:_ a run emits one ledger row per call with model id; budget-exhausted
    halts the rewrite stage (never-fail-open: halt honestly, do not skip verify).

- **W5. Wire the stage into the ingestion pipeline.** After extraction records
  items for a changed document, the rewrite stage runs over those items under the
  run lock / timeout / sub-budget already in place. City-published-Spanish skip
  (§36b, body_id + meeting date) short-circuits the ES chain for those meetings.
  - _Verify:_ pipeline test on stored fixtures (no live fetch): a changed document
    produces verified items; an unchanged run does nothing (idempotent).

- **W6. One live end-to-end run (INFRA-PROPOSE, the finale).** Against a real
  Ventura agenda already in storage (no re-fetch, §40b): extract → rewrite → verify
  → persist, with Nova Lite live. Report per-item what verified in each language,
  the rejection count, and total cost from the ledger.
  - _Verify:_ the run completes; every shown item has a receipt from the record;
    no unverified rewrite is stored; cost is recorded and within sub-budget. This is
    the "it actually works on a real agenda" gate.

## Sequencing

W1 → W2 → W3 in order (each builds on the last), W4 alongside W3, W5 after W3+W4,
W6 last and PROPOSE-and-wait (it spends, though pennies). W1-W5 are offline
(stub/fixture/DB) and cost nothing; only W6 makes live calls.

## Not in scope here

- The public site / view rendering (Spec 6) — the contract exists (`web/contract.py`),
  but wiring the site is a later spec.
- Search (Spec 4), the watcher (Spec 5).
- Task 0b golden items (deferred; trigger recorded).
- Re-deriving thresholds on a larger corpus (v2 / task 0b).
