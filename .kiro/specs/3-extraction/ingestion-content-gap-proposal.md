# Root-cause task PROPOSAL — ingestion stores metadata, not content (propose only)

Status: **PROPOSE ONLY.** Not built. Surfaced during W6: the three symptoms below
are one bug.

## The one bug, three symptoms

Spec 2 ingestion records document METADATA (id = content hash, url, headers,
status) but never the document's CONTENT, and extraction was never wired into the
pipeline. Observed in live Aurora `porchlight-dev` (2026-08-30):

1. **`items` is empty (0 rows).** The extractor agent exists and is tested, but it
   was never run over stored documents, so no items exist.
2. **No document text is persisted anywhere.** `documents` has no text column;
   `items` has `item_number`/`page_start`/`page_end`/`embedding` but no text. The
   verbatim page-range text the rewrite chain needs has no home.
3. **`documents.role` is `""` on all 15 rows.** The classifier works and is tested,
   but ingestion never wrote its output into the `role` column.

W6 proved extract→rewrite→verify→persist works on real unseen text ONLY by fetching
one agenda and extracting in memory. It did NOT prove ingestion feeds that chain,
because of the above.

## Proposed tasks (propose only; each verifiable; W6-style single-doc before any sweep)

- **R1. Persist role at ingestion.** Wire `classify()`'s output into the `role`
  column when a document is recorded (it is already computed; it just is not
  stored). Smallest fix, unblocks §36b and role-keyed logic.
  - _Verify:_ DB test — a recorded document has the classifier's role, not "".

- **R2. Persist document text + a page map at ingestion.** Add storage for the
  extracted text layer (per-page, so page ranges are recoverable) — either a
  `document_text` table or a text column, decided in the task. Text is fetched ONCE
  when the document is first recorded (the fetch already happens for hashing; reuse
  those bytes — no second request, §40b). pypdf becomes a runtime dependency here
  (promoted from dev, as flagged).
  - _Verify:_ DB test — a recorded document round-trips its text + page map; a
    re-record of identical bytes does not duplicate (content-hash idempotent).

- **R3. Wire extraction into the pipeline.** After a changed document is recorded
  (with text, R2), run the extractor over its stored text to produce `items` rows
  (item_number + page range copied from source, the fidelity guard already built).
  Under the run lock / caps / partial-read already in place.
  - _Verify:_ pipeline test on a stored fixture doc — items appear with page ranges;
    an oversized doc fires the cap and marks partial (existing behavior).

- **R4. Wire the rewrite stage after extraction.** The W1-W5 stage runs over the
  items R3 produced (reading their stored text), persisting `item_rewrites`. This
  closes the loop: ingestion → extract → rewrite → verify → persist, from storage.
  - _Verify:_ pipeline test — a changed document ends with verified `item_rewrites`
    rows sourced entirely from storage (no in-memory hand-off, unlike W6).

- **R5. Deploy the schema + backfill one meeting live (INFRA-PROPOSE).** Apply
  migrations (002 model_id, 003 item_rewrites, plus R1/R2's) to Aurora; run the full
  chain against ONE real stored meeting end-to-end from storage. This is the "W6 but
  actually from the pipeline" gate. Propose-and-wait (it spends, pennies).

## Sequencing

R1 → R2 → R3 → R4 offline (DB/fixtures, free); R5 last and propose-and-wait.
R1 alone is a small, high-value fix (role is computed, just unpersisted) and could
ship first on its own.

## Not in scope

- Backfilling all 15 (or 152) documents — R5 does one; a full backfill is a
  follow-on once the chain is proven from storage.
- The public site (Spec 6), search (Spec 4), watcher (Spec 5).
