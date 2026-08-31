# Requirements Document — Spec 5: The Watcher (live match, plain reason, draft structure)

## Introduction

Spec 5 builds the second of the two agents and the one the product is named for.
The watcher watches one person's list. When a stored, verified item is relevant to
something that person cares about, the watcher says so, in plain English and
Spanish, with the receipt already attached, and it offers the structure of a public
comment. It is the moment the pipeline stops being infrastructure and becomes the
thing the primary user opens on a Friday.

Two design facts govern the whole block, both already decided in the steering rules
and recorded here as requirements rather than left implicit:

1. **The watcher is invoked live, not scheduled (§26c).** Hunter and extractor run
   hourly on a schedule and write to storage. The watcher runs when a person opens
   the page: the browser sends the watchlist, the agent answers over the already
   ingested-and-verified items, and **nothing about that person is stored.** This is
   the opposite ingestion model from Specs 2 and 3, and the security posture around
   it (a fourth, narrower identity; no credentials in the browser) is a requirement,
   not a detail.

2. **The watcher decides relevance and emits its reason in the same breath.** Job 2
   of the model's three jobs (model-authority.md) is "decide whether an item is
   relevant to one person's watchlist, emitting the match AND its plain-language
   reason in one structured output." A second call to explain a decision already
   made is confabulation and is banned (never.md #10). The match and the reason are
   one output or they are not trusted.

The watcher reads what Spec 3 wrote: `items` (item number, page range), the verified
`item_rewrites` (plain EN/ES that already passed the six-check verifier), and the
receipt fields on `meetings`/`bodies`/`documents`. It writes to no table. Its output
is the `web/contract.py` view shape (the `ChangedItem` card and the quiet-week
`View`), so Spec 6 is a path swap, not a reshape (§25).

References §26c (live invocation, fourth identity), §2/§8 (never assert a fact you
could miss a deadline over), model-authority.md job 2 (relevance + reason, one
output; errs toward showing), never.md #1/#5/#6/#8/#10, voice.md (plain-first,
bilingual equal weight, the reserved amber, absence phrasing), security.md (input
validation both sides, watch-term caps, share-link handling, watcher spend
sub-budget, no egress from the model call). The `never.md` and `model-authority.md`
rules govern throughout.

## Rigor budget (style.md)

A model in the loop deciding relevance, so **working rigor on real Ventura items**,
plus **property/behavioral tests on the two invisible-failure surfaces specific to
this block:**

1. **The bias-toward-showing invariant.** A false negative is a missed deadline; a
   false positive is a mild annoyance (model-authority.md). The test surface is: a
   plausibly-relevant item is never silently dropped, and a match is never emitted
   without its reason and its receipt. A watcher that quietly hides a real match is
   this block's worst invisible failure — it is exactly the miss the product exists
   to prevent.

2. **The no-store invariant.** The watchlist and any draft live in the browser
   (never.md #8). The test surface is: the live request path writes nothing about
   the user to any store, and the codebase contains no watchlist/draft persistence
   and no shared/public-watchlist path. This is tested structurally (no such code
   exists) the way the draft's empty-stance guarantee is (§4b).

Relevance is tested against captured real items and a hand-built watchlist set,
never against a description of what the model "should" match (testing.md). The
receipt, the deadline, and the match reason's factual anchors are checked by code,
not trusted from the model.

## Glossary

- **Watchlist**: the set of terms one person cares about ("short-term rentals",
  "the pier", "traffic on Main"). Lives in the browser, sent with the request,
  never stored server-side (never.md #8).
- **Watcher**: the AgentCore agent (Strands) that, given a watchlist and the stored
  verified items, decides relevance and emits each match with its reason. Cap 5
  turns, hard token cap (tech.md). Reads items/rewrites; writes nothing.
- **Match**: one relevant item for this watchlist, carrying the item's verified
  plain-language summary, the **reason it matched** (emitted in the same structured
  output, never.md #10), and the receipt copied from the record.
- **Reason**: the plain-language sentence saying why the item is relevant to a
  watch term. Bilingual, model-authored, but carries **no** date/deadline/item
  number/page/body/URL (never.md #1) — those are the receipt, attached from the
  record.
- **Quiet week**: the most-seen and most-important screen — no match, said
  honestly. "Nothing new for you this week" is a complete, correct answer (voice.md).
- **Fourth identity**: the request-time credential Vercel uses to invoke the watcher
  runtime, scoped to the watcher alone — narrower than the three execution roles
  (§26c). No AWS credentials ever reach the browser.

## Requirements

### Requirement 1: The watcher agent — relevance and reason in one structured output

**User Story:** As the weekly watcher, I want to be told which of this week's items
touch what I care about, and why, in one honest answer, so that I do not have to
read twenty agendas to find the one that matters.

#### Acceptance Criteria

1. THE Watcher SHALL be an AgentCore agent (Strands), given a watchlist and reading
   the stored **verified** items (`items` + `item_rewrites`), and SHALL emit, for
   each relevant item, the match AND its plain-language reason in **one structured
   output** (model-authority.md job 2, never.md #10). A second call to explain a
   match is forbidden.
2. THE Watcher's relevance decision SHALL **err toward showing**: when relevance is
   uncertain, the item is shown, because a false negative is a missed deadline and a
   false positive is a mild annoyance (model-authority.md). This bias is a stated,
   tested property, not an accident of prompting.
3. THE reason string SHALL be model-authored plain language in **both EN and ES**
   (voice.md equal weight) and SHALL contain **no** date, deadline, item number,
   page range, body name, or URL — those are the receipt, copied from the record
   (never.md #1, #6). A reason that restates a deadline the model invented is a
   never.md #1 violation even if it happens to be correct.
4. THE Watcher SHALL have a **hard turn cap of 5 and a hard token cap** (tech.md);
   a cap firing is logged and surfaced, not an error. WHEN the cap fires before the
   list is fully assessed, THE Watcher SHALL return the matches found so far and
   mark the answer **partial**, never silently present a partial pass as complete
   (§16b), and never discard found matches.
5. THE Watcher's model id SHALL be read from configuration (never hardcoded) and
   appear in every structured log event, so a run is attributable (§27, tech.md).
6. THE Watcher SHALL log with the shared structured schema (`component="watcher"`,
   `run_id` on every line); logs SHALL NEVER contain packet/item text (security.md).

### Requirement 2: Live invocation, and the fourth identity (§26c)

**User Story:** As the person being watched for, I want the watching to happen when
I ask and to leave no trace of me, so that using this tool costs me no privacy.

#### Acceptance Criteria

1. THE Watcher SHALL be invoked **at request time** when a person opens the page —
   not on a schedule (§26c). The browser sends the watchlist; the agent answers over
   already-ingested items; the request completes.
2. THE invocation SHALL use a **fourth IAM identity scoped to the watcher runtime
   alone** — narrower than the hunter/extractor/pipeline roles (§26c). This identity
   MAY read the items/rewrites it needs and invoke the watcher runtime; it SHALL NOT
   carry write access to ingestion tables or the ability to invoke the other agents
   from the browser path.
3. **No AWS credentials SHALL ever reach the browser** (§26c, security.md). The
   browser talks to a read-only endpoint (Spec 6 surface); that server-side endpoint
   holds the fourth identity and invokes the watcher. Credentials live server-side
   only (security.md).
4. THE live watcher path SHALL have its **own spend sub-budget**, separate from
   ingestion, so that request-time model calls cannot starve the scheduled pipeline
   and the spend ledger halting is not itself an attack surface (security.md). WHEN
   the watcher sub-budget is exhausted, the request SHALL return an honest degraded
   state (Requirement 5), never a fabricated match and never a silent empty.
5. THE public request path SHALL be **rate-limited per IP** (security.md), and the
   rate-limit rejection SHALL be an honest state, never a blank screen.

### Requirement 3: The watchlist never leaves the browser (never.md #8)

**User Story:** As a resident, I want my list of concerns to be mine, on my device,
so that watching the city never becomes the city (or anyone) watching me.

#### Acceptance Criteria

1. THE Watchlist SHALL live in the browser and be **sent with the request, never
   stored server-side** (never.md #8). No table, no log, no cache persists a user's
   watchlist or the association between a watchlist and a person.
2. THE System SHALL contain **no shared or public watchlist** capability — not a
   feature, not a stub, not a dead path (never.md #8). This is enforced structurally
   (no such code path exists), tested the way empty-stance is (§4b).
3. Drafts (Requirement 6 output) SHALL likewise **not be stored server-side**
   (never.md #8); a draft is assembled and returned, and lives in the browser.
4. THE product copy describing this SHALL be the verbatim, load-bearing strings
   (voice.md): **"Your list stays on your device. We use it to answer, and never
   store it."** These SHALL NOT be reverted to any wording that claims we never see
   the list — the watcher matches from a transmitted watchlist, so "we never see it"
   is untrue (voice.md §26c note). The truer, weaker wording stands.
5. THE watch input SHALL be validated **client-side AND server-side** (security.md,
   never trust the front end): a per-term length cap, a per-list count cap, and
   character validation, each with a stated value and a one-line rationale
   (style.md). The caps are a requirement; their exact numbers are set in design.

### Requirement 4: Share links carry the list in the fragment, and are confirmed (never.md #8)

**User Story:** As someone who found a useful set of watch terms, I want to share
them with a neighbor without a server ever holding either of our lists, and without
silently overwriting theirs.

#### Acceptance Criteria

1. A shared watch link SHALL carry the terms in the **URL fragment** (`#...`),
   **never a query string** (never.md #8), so the terms are never sent to or logged
   by the server.
2. A shared list SHALL be **shown and confirmed before it is applied, never
   auto-applied** (security.md, never.md #8). The recipient sees the incoming terms
   and chooses to accept them; an opened link never silently replaces their list.
3. THE incoming shared terms SHALL pass the same validation as typed terms
   (Requirement 3.5) before they can be confirmed.

### Requirement 5: Honest empty and degraded states — never fail open (never.md #7)

**User Story:** As a watcher, I want a quiet week to look like a quiet week and a
broken dependency to look broken, so that I never mistake a failure for "all clear"
and miss something.

#### Acceptance Criteria

1. WHEN no item matches the watchlist, THE Watcher SHALL return the **quiet-week
   state** honestly — the `View.is_quiet` shape — and the copy SHALL be a complete,
   calm answer ("Nothing new for you this week"), never an apology and never implying
   the user did something wrong (voice.md). The quiet week is the product working.
2. WHEN a dependency is degraded (the model call fails, the sub-budget is exhausted,
   items cannot be read), THE Watcher SHALL return an **honest empty/degraded state
   that says so**, never a fabricated match and never a silent all-clear (never.md
   #7). A degraded answer is distinguishable from a quiet week — a quiet week means
   "we looked and found nothing," degraded means "we could not fully look."
3. THE System SHALL NEVER perform a **silent model fallback to another provider**
   (never.md #7); a degraded model dependency produces the honest degraded state.
4. Every caught error on the request path SHALL be written to the failure log
   (never.md #12, security.md); no exception is silently swallowed, and the user
   sees a meaningful state with `aria-live`, never a blank screen or endless spinner.

### Requirement 6: The matched card carries its receipt and offers a draft (never.md #6)

**User Story:** As a watcher who is about to act, I want every claim to show its
source and to hand me a comment I can finish, so that I can trust it and use it in
one sitting.

#### Acceptance Criteria

1. Each match SHALL be rendered as the **`ChangedItem` contract shape**
   (`web/contract.py`): status chip (`mark` + word, meaning surviving greyscale),
   the plain heading with the **official term adjacent** (voice.md), the match
   reason, the page-scale note, the receipt, the deadline, and one action. The
   watcher produces this shape so Spec 6 is a path swap (§25).
2. THE receipt SHALL be **copied from the record** — body, meeting date, item
   number, page range, source link (never.md #6) — never authored by the model. The
   contract has no field a model could write a receipt into (already enforced by
   `web/contract.py`); the watcher populates receipt fields only from
   items/meetings/bodies/documents.
3. THE deadline SHALL be **copied from source or not shown** (never.md #1), rendered
   in **city local time, always labeled** (voice.md, Spec 3 deadline renderer), and
   the reserved `--deadline` amber (`deadline_actionable`) SHALL be set **only** for
   an approaching comment deadline the user can still act on — nowhere else (voice.md).
4. THE card's action SHALL offer to start a comment, producing the **draft scaffold**
   (Spec 3 `draft/scaffold.py`): facts + receipt + logistics, **stance fields empty
   by construction**, **no send capability** (never.md #4, #5). The watcher assembles
   structure from verified facts and never writes a position.
5. THE shown summary SHALL be the **verified** rewrite from `item_rewrites` (or the
   honest EN/ES fallback already stored there, never.md #7) — the watcher never
   re-summarizes and never generates a fact (never.md #1). The watcher decides
   relevance over verified text; it does not produce new claims.

### Requirement 7: Never rank, score, or aggregate a public body (never.md #2, #3)

**User Story:** As the project, I want the watcher incapable of turning into a
surveillance or harassment tool, so that a good-neighbor tool stays one.

#### Acceptance Criteria

1. THE Watcher SHALL NOT score, grade, rank, sum, or count anything **per public
   body** (never.md #2). No "this body posts late" metric, no tally of matches by
   body. The aggregation mechanism is never built, because the mechanism is the
   harm.
2. THE Watcher SHALL NOT say or encode "overdue", "late", "missing", "delayed", or
   "failed" about a public body — in copy, in rendered comment, or in color
   (never.md #3, voice.md). Absence is exactly **"not located at [url] as of
   [timestamp]"** and nothing else.
3. Relevance is judged **item to watchlist**, never body to a quality judgment. The
   watcher ranks nothing; it includes or it does not.

### Requirement 8: Untrusted input containment on the live path (security.md, never.md #9)

**User Story:** As the project, I want the request-time model call to be as
contained as the extractor, so that a hostile watchlist or a poisoned item cannot
turn the watcher into a weapon.

#### Acceptance Criteria

1. THE watchlist and the item text the watcher reads SHALL be treated as **untrusted
   data, never instruction** (never.md #9). An injected "ignore your instructions"
   in a watch term or an item is data to match against, never a command.
2. THE Watcher's tools (if any) SHALL be **allowlisted at the Strands hook layer**,
   and a blocked tool call SHALL be logged as a NEVER-trip (security.md, never.md #9)
   — the same control proven live for the extractor (§42b: the test exercises the
   control by NAME, with a benign non-allowlisted tool).
3. WHERE the watcher is wired to call the extractor as a tool (Agent-as-Tool,
   tech.md — watcher may call extractor; nothing calls outward), that call SHALL be
   the only outward agent call it can make; the watcher SHALL NOT reach the network
   directly.
4. THE watcher's answer SHALL be structured output the server validates against the
   contract before returning it; a malformed or off-contract model answer is a
   degraded state (Requirement 5), never passed through to the browser.

### Requirement 9: Bilingual by construction, correct in both (voice.md)

**User Story:** As a Spanish-reading resident, I want the watcher's answer to be as
complete and correct in Spanish as in English, so that the tool is mine too.

#### Acceptance Criteria

1. Every user-facing string the watcher produces or the card renders SHALL exist in
   **English and Spanish, equal weight, correct `lang` attributes** (voice.md). This
   includes the match reason, the quiet-week copy, and every degraded state.
2. Spanish SHALL be checked for gendered second-person and role nouns (voice.md:
   English can be gender-neutral by accident, Spanish cannot). The provisional
   Spanish greeting **"Buenas tardes, vecindad."** and the verbatim privacy string's
   Spanish stand pending fluent review, and the README/limitations note the pending
   review honestly.
3. THE match reason's Spanish SHALL be the model's plain-language reason in Spanish;
   because the reason carries no receipt entities (Requirement 1.3), it needs no
   entity verification, but it SHALL be produced in the same structured output as the
   English reason (one call, never.md #10), not a follow-up translation call that
   would re-open the two-call ban.

## Pass gate for this block

1. Given a real watchlist and the real stored verified items, the watcher returns
   matches, each with its reason **and** its receipt, in one structured output —
   demonstrated on captured real data.
2. The bias-toward-showing property holds: a plausibly-relevant item is shown, and
   no match is ever emitted without a reason and a receipt (tested).
3. The no-store invariant holds: the request path writes nothing about the user, and
   the codebase contains no watchlist/draft persistence and no shared-watchlist path
   (tested structurally).
4. A quiet week renders the honest quiet-week state; a forced degraded dependency
   renders an honest degraded state distinguishable from a quiet week; neither
   fabricates a match (never.md #7).
5. The turn/token cap demonstrably fires on an oversized watchlist and returns a
   marked-partial answer with the matches found, never silence and never a claimed
   completion (§16b).
6. A share link round-trips through the URL fragment and is shown-and-confirmed
   before applying, never auto-applied; incoming terms pass validation.
7. The tool-allowlist NEVER-trip fires on a non-allowlisted tool on the watcher, the
   same control proven for the extractor (a benign non-allowlisted tool, §42b).
8. Every user-facing string is present in EN and ES with correct `lang`; the pending
   Spanish-review items are listed honestly.

## Explicitly out of scope for Spec 5

- The public site itself and the read-only search endpoint (Spec 6) — Spec 5
  produces the contract-shaped answer and the server-side invocation seam, but the
  HTML surface, the search box, and the deployment to Vercel are Spec 6.
- Embeddings and vector/lexical/fusion search ranking (Spec 4) — the watcher decides
  relevance over the stored verified items; the search vocabulary-bridge and ranking
  are a separate block. Where Spec 4 lands first, the watcher may use it; the
  requirement here does not assume it.
- Any change to how items are extracted or rewritten (Spec 3) — the watcher reads
  verified rewrites and never re-summarizes.
- Choosing the watcher's model on measured evidence — the model id is config-read
  (Requirement 1.5); a watcher-specific model comparison, if wanted, is a design/
  later decision, not a requirement of this block.
