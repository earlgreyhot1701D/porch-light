# Implementation Plan: Spec 5 — The Watcher (minimal, read-only matcher)

## Overview

Build the second agent: given a watchlist (from the browser) and the stored
**verified** items, decide relevance and emit each match with its reason in **one
structured output** (never.md #10), carry the receipt copied from the record, and
offer the stance-free draft scaffold. It reads `items` + `item_rewrites` +
receipt fields; it **writes nothing**. Approved requirements govern.

**No design.md — deliberate (working style / §28 anti-pattern).** A read-only
matcher that consumes existing tables and emits the existing `web/contract.py`
shape has no data model to design. Writing a design doc here would be Block-Zero
rigor on something that does not need it. The requirements + this task file are the
plan; the contract already exists in code.

**Resolved choices (from approval, recorded so they do not drift):**
- Watch-term caps: **10 terms, 60 chars each** — PoC judgment calls (Requirement 3.5).
- Model: **Nova Lite, config-read, no watcher-specific bake-off** (out-of-scope note).

**Dependency reality (from the sweep):** `items`/`item_rewrites` are **0 rows** in
Aurora. The watcher can be BUILT and unit/behaviorally tested against captured/
fixture items now, but it cannot be proven end-to-end on real stored data until the
**condition-5 join** (Spec 3 R5) lands real items + rewrites for ≥2 meetings. That
join is sequenced BEFORE this block in the overall build order (a → b), so by the
time the watcher runs live the data exists. Tasks here that need real stored rows
are marked **[NEEDS-C5]** and gate only the live-proof task, not the build.

Rigor budget (style.md): **working rigor on real/captured items + behavioral tests
on the two invisible-failure surfaces of THIS block — the bias-toward-showing
invariant and the no-store invariant.** Relevance is tested against captured items +
a hand-built watchlist set, never a description of what the model "should" match
(testing.md). Block-by-block with a PASS/FAIL QA checkpoint before the next block.

Tags: [PERMANENT] ships. [TEST]. [NEEDS-C5] needs real stored items to prove live.
[INFRA-PROPOSE] billable/external state — propose and wait.

## Tasks

- [ ] 1. [PERMANENT] Watch-input validation — pure, shared by client and server (R3.5, R4.3)
  - [ ] 1.1 `src/porchlight/watch/validate.py`: pure function validating a watchlist
    - Enforce ≤10 terms, ≤60 chars/term, character validation (printable, no control chars); return normalized terms + a structured rejection reason. No I/O, no model. This is the server half of "validate both sides" (security.md); the JS client half mirrors it in Spec 6.
    - One responsibility: input validation only. Every cap has its value + one-line rationale in the module docstring.
    - _Requirements: R3.5, R4.3, security.md_
  - [ ] 1.2 [TEST] Property/unit tests: at-cap passes, over-cap rejects with a reason, control chars rejected, incoming shared-link terms take the same path
    - _Requirements: R3.5, R4.2, R4.3_
  - **QA checkpoint (PASS/FAIL): validation rejects the over-cap and hostile cases and passes real terms, before any matcher work.**

- [ ] 2. [PERMANENT] Match contract types — what the watcher emits (R1.1, R1.3, R6.1)
  - [ ] 2.1 `src/porchlight/watch/models.py`: the structured match output
    - A `WatchMatch` carrying: `item_id`, the bilingual `match_reason` (model-authored, NO receipt entities), and the verified summary reference — plus the fields needed to assemble a `ChangedItem`. A `WatchAnswer` wrapping matches + `is_partial` + a `degraded` flag (R1.4, R5.2). Reason and match are ONE object (never.md #10): there is no code path that sets a reason separately from its match.
    - Frozen dataclasses, no model, no I/O. The reason field accepts model text; the receipt fields do NOT exist on this type (they are attached later from the record), so the model has nothing to author a receipt into (never.md #6).
    - _Requirements: R1.1, R1.3, R6.1, R6.2, never.md #10_
  - [ ] 2.2 [TEST] A match cannot be constructed without its reason; the type has no receipt/deadline/body field a model could fill
    - _Requirements: R1.1, R6.2, never.md #6, #10_

- [ ] 3. [PERMANENT] The relevance matcher — the model's job 2, one structured output (R1)
  - [ ] 3.1 `src/porchlight/watch/matcher.py`: build the Strands agent (Nova Lite, config-read) that takes a validated watchlist + verified items and returns a `WatchAnswer`
    - Temperature ~0, structured output. Prompt instructs: decide relevance per item, and for each relevant item emit its plain-language reason IN THE SAME OUTPUT (never a second call). Bias toward showing: when uncertain, include (Requirement 1.2). Reason carries no date/number/id/body/URL (Requirement 1.3) — those are the receipt.
    - Caps: turn cap 5, hard token cap (tech.md); a cap firing returns matches-so-far with `is_partial=True` (R1.4), logged and surfaced, never silent, never discarding found matches.
    - Model id read from `BEDROCK_MODEL_ID`, in every log line; `component="watcher"`, `run_id` per line; logs never contain item text (R1.5, R1.6, security.md).
    - _Requirements: R1.1–R1.6, model-authority.md job 2_
  - [ ] 3.2 [PERMANENT] Tool allowlist hook — same control proven for the extractor (R8.2)
    - Reuse the extractor's allowlist-hook pattern (`strands.hooks.BeforeToolCallEvent`, fail-closed, NEVER-trip log). The watcher's tool surface is minimal (it reads items handed to it); a non-allowlisted tool call is blocked and logged. If the watcher is wired Agent-as-Tool to the extractor, that is the only outward agent call (R8.3).
    - _Requirements: R8.1–R8.4, never.md #9, §42b_
  - [ ] 3.3 [TEST] Behavioral tests on captured real items + a hand-built watchlist
    - Bias-toward-showing: a plausibly-relevant item is included; no match is emitted without a reason (assert on the type + on real model output). An off-topic watchlist yields the quiet state. A watch term containing an injected instruction is matched as DATA, never obeyed (never.md #9). Oversized watchlist trips the cap → marked partial, matches-so-far kept. Tests use captured items, never a "should return" description (testing.md).
    - _Requirements: R1.2, R1.4, R5.1, R7.3, R8.1, testing.md_
  - **QA checkpoint (PASS/FAIL): on captured items, the matcher emits match+reason in one output, errs toward showing, and trips the cap honestly — before wiring receipts or the live seam.**

- [ ] 4. [PERMANENT] Assemble the ChangedItem card — receipt + deadline + draft, all copied from the record (R6)
  - [ ] 4.1 `src/porchlight/watch/assemble.py`: pure function `WatchMatch + record rows → ChangedItem` (web/contract.py)
    - Populate receipt (body, meeting date, item number, page range, source link) ONLY from items/meetings/bodies/documents rows (never.md #6). Deadline copied from source or None, rendered city-local labeled via the Spec 3 deadline renderer; set `deadline_actionable` only for an approaching still-actionable comment deadline (voice.md). Shown summary = verified `item_rewrites` text (or the stored honest EN/ES fallback), never re-summarized (R6.5, never.md #7). Official term adjacent to plain term (voice.md).
    - Pure, no model, no I/O. This is where the model's reason meets the code's receipt; the seam is the guarantee that a receipt is never model-authored.
    - _Requirements: R6.1–R6.5, R7.2, voice.md, never.md #1, #6_
  - [ ] 4.2 [PERMANENT] Draft action → `draft/scaffold.py` (already built): the card's "start a comment" assembles the stance-free scaffold
    - Wire the existing `build_scaffold` (facts + receipt + logistics, empty stance, no send). No new draft code; no send path anywhere (never.md #4, #5).
    - _Requirements: R6.4, never.md #4, #5_
  - [ ] 4.3 [TEST] Card assembly copies receipt from the record and never from the match; deadline is source-or-None; amber only when actionable; a two-failure item shows original text
    - _Requirements: R6.2, R6.3, R6.5, never.md #1, #6, #7_

- [ ] 5. [PERMANENT] Honest empty vs degraded — never fail open (R5)
  - [ ] 5.1 In the matcher/answer path: distinguish quiet (looked, found nothing → `View.is_quiet`) from degraded (could not fully look → explicit degraded state)
    - Model failure, sub-budget exhaustion, or unreadable items produce a degraded answer that SAYS so; never a fabricated match, never a silent all-clear (never.md #7). No silent provider fallback (R5.3). Every caught error writes to the failure log (never.md #12); nothing swallowed.
    - _Requirements: R5.1–R5.4, never.md #7, #12_
  - [ ] 5.2 [TEST] Forced model failure → degraded (distinguishable from quiet); empty watchlist result → quiet; both assert no fabricated match
    - _Requirements: R5.1, R5.2, R5.4_
  - **QA checkpoint (PASS/FAIL): quiet and degraded are distinguishable and neither fabricates — before the live seam can return either to a browser.**

- [ ] 6. [PERMANENT] The no-store invariant — structural (R3.1–R3.3, never.md #8)
  - [ ] 6.1 Confirm-and-document that the watch path persists nothing about the user
    - The matcher takes the watchlist as an argument and returns an answer; no table write, no cache of watchlist↔person, no draft persistence. Add a module-level docstring stating the invariant (like the draft's empty-stance note) and a `grep`-able guard test.
    - _Requirements: R3.1, R3.3, never.md #8_
  - [ ] 6.2 [TEST] Structural: the watch package contains no persistence call and no shared/public-watchlist path (assert by construction, the way empty-stance is tested)
    - _Requirements: R3.2, never.md #8_

- [ ] 7. [PERMANENT] Bilingual output + verbatim privacy strings (R3.4, R9)
  - [ ] 7.1 The quiet-week copy, the degraded copy, and the privacy string as bilingual constants
    - Verbatim, non-negotiable (voice.md): **"Your list stays on your device. We use it to answer, and never store it."** and its ES. Quiet-week EN "Nothing new for you this week" + ES. Provisional ES greeting "Buenas tardes, vecindad." Correct `lang` attributes are Spec 6's render concern; the strings + their ES live here. ES second-person/role nouns checked for gender; pending fluent review noted (README/limitations).
    - The reason's ES is emitted by the matcher in the same output as EN (Requirement 9.3), not a follow-up call.
    - _Requirements: R3.4, R9.1–R9.3, voice.md_
  - [ ] 7.2 [TEST] Every watcher-produced user-facing string has EN and ES; the privacy string is exactly the approved wording and no code claims "we never see the list"
    - _Requirements: R3.4, R9.1, voice.md_

- [ ] 8. [NEEDS-C5] Live proof on real stored data — one real watchlist over ≥2 real meetings
  - [ ] 8.1 After the condition-5 join has put real items + verified rewrites in Aurora, run the watcher against a real watchlist and print the full answer
    - Show: matches with reason + receipt (receipt spot-checked against the real PDF), a quiet result for an off-topic list, the cap firing on an oversized list. This is the pass-gate demonstration (Requirement 1 pass gate) and the demo's watcher beat.
    - Gated by Spec 3 condition-5 (real rows). Does NOT gate tasks 1–7 (built/tested on captured items).
    - _Requirements: R1 pass gate, R6.2_
  - [ ] 8.2 [INFRA-PROPOSE] Deploy the watcher as its own AgentCore runtime + the fourth IAM identity + spend sub-budget (R2)
    - Billable persistent external state — **propose and wait.** Fourth identity scoped to the watcher runtime alone; server-side only (no creds to browser); watcher spend sub-budget; per-IP rate limit. Sequence with the Spec 6 web surface (they share the request seam). Present options + cost before deploying.
    - _Requirements: R2.1–R2.5, security.md, §26c_

## Pass gate for this block

1. On captured real items + a real watchlist, the matcher emits match + reason in
   one structured output, errs toward showing, and trips the cap honestly (tasks 3).
2. The card carries a receipt copied from the record and offers the stance-free
   draft; nothing is model-authored that should be copied (task 4).
3. Quiet and degraded are distinguishable; neither fabricates a match (task 5).
4. The no-store invariant holds structurally: no watchlist/draft persistence, no
   shared-watchlist path (task 6).
5. Every watcher-produced string is EN + ES; the privacy string is verbatim (task 7).
6. **[NEEDS-C5]** On real stored data for ≥2 meetings, one real watchlist returns
   matches with spot-checked receipts (task 8.1) — the demo's watcher beat.

## Explicitly out of scope for Spec 5

- The HTML surface, the search box, the client-side validation mirror, and the
  Vercel deployment (Spec 6). This block produces the matcher + the contract-shaped
  answer + the server-side invocation seam design; Spec 6 renders and deploys.
- Embeddings / vector-lexical-fusion search ranking — **Spec 4 is CUT** (not
  deferred): unnecessary at this scope (one city, one adapter, tens of items). The
  watcher decides relevance directly over the stored items; a vocabulary bridge +
  lexical + vector + rank-fusion search stack is engineering for a corpus we do not
  have. Vector search is a v2 concern for when the corpus is large enough to need it.
  See KNOWN-LIMITATIONS "Spec 4 (search) is cut, not deferred" for why the cut is
  safe (the matcher is a replaceable seam; `items.embedding` exists unused; per-item
  text is stored so embedding later needs no re-fetch).
- Any change to extraction or rewrite (Spec 3); the watcher reads verified rewrites.
