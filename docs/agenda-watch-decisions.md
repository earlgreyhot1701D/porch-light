# Agenda Watch (hackathon build) — Running Decisions Log

**Hackathon:** Agents for Humans (AWS + Devpost). Closes Sep 14, 2026, 5:00 PM PT.
**Track:** Good Neighbor Agents.
**Companion doc:** `claude/agents-for-humans-brief.md` (rules, criteria, checklist). That doc governs. This one records decisions.
**Status:** Pre-PRD. Decisions below are settled unless marked OPEN.

**Provenance:** the idea predates the hackathon. A weekend prototype exists at https://github.com/earlgreyhot1701D/civiq. **No code from it is used.** New repo, first commit after Aug 10, 2026. A disclosure line goes in the README and the Devpost description naming the prior prototype and stating no code was reused. The pre-hackathon handoff doc and the v0.4 HTML mock are design inputs, not source. The mock is being rebuilt, not imported.

---

## 1. What we are building

An agent that watches a city's public meeting agendas on behalf of a specific person, and tells them when something they care about lands, in plain English and in Spanish, with a receipt attached to every claim. It drafts a public comment. A human sends it.

**Primary user: the weekly watcher.** The neighborhood association volunteer, the nonprofit advocacy staffer, the parent tracking the school board and parks commission, the library friends group watching the budget committee. The person who currently opens twenty city pages every Friday night and still misses the supplemental packet that posted Tuesday morning.

**Secondary user: the resident.** Plain-language search, public, free, no login. Not the agent's customer, but the front door.

The persona moved from the resident to the watcher because the hackathon mandate is a **routine, repetitive task**, and the resident does this once a year while the watcher does it every week. The change also makes the system honestly agentic: a standing watch is a real agent job, a scheduled pipeline is not.

**Scope: City of Ventura only.** Adapter written as a CivicPlus vendor adapter, not a Ventura adapter.

---

## 2. Deterministic vs model

The line that sells the build: **the model translates and it notices. It never asserts a fact you could miss a deadline over.**

**Deterministic, no model:** listing page fetch, conditional GET, content hashing, change detection. Body, meeting date, posting timestamp, source URL. Document role (agenda / amended / supplemental / cancellation / Spanish edition). Item numbers and page ranges from the PDF text layer. Comment deadlines copied from source. The vocabulary bridge. Lexical search, rank fusion, spend ledger, run log, every status string, every receipt.

**Model, three jobs only:**
1. Rewrite staff language into plain English. English and Spanish.
2. Decide whether an item is relevant to a named person's watchlist.
3. Assemble the *structure* of a public comment draft. Never its stance (see §4b).

**Model, never:** any date, deadline, item number, page range, body name, or URL. Any assertion that something does not exist. **Any political position, opinion, or recommendation on behalf of a person.** Any tool call outside its scope. Enforced by Strands hooks at runtime, not by prompt.

**Time is deterministic, and it is the highest-harm field in the system.** Comment deadlines are stored with an explicit timezone, rendered in **city local time**, always labeled with the zone, and **never silently converted to the viewer's local time.** A watcher may be traveling, on a phone set to another zone, or in a browser that resolved UTC. Relative phrasing ("closes tomorrow at 5") is computed against city time, never the browser clock. DST boundaries get an explicit test case. Getting a deadline wrong is the one failure this project ranked above all others, so nothing about time is inferred.

---

## 3. Agent surface map

ReAct applies to three places. Everything else is a function call.

### Loop 1 — Hunter
**Job:** find what changed on the city's site since the last run. Never reads a packet.

| Tool | Does | Constraint |
| --- | --- | --- |
| `list_bodies()` | Returns the 21 bodies from the adapter | Static config. No network. |
| `fetch_listing(body_id)` | Conditional GET on one body's page | Allowlisted host only. Backoff on 429/503. |
| `fetch_document_head(url)` | Metadata and content hash, no body download | Allowlisted host only. |
| `classify_document(metadata)` | Deterministic role classification: agenda, amended, supplemental, cancellation, Spanish edition | Pure function. No model. |
| `record_document(...)` | Writes the document row | Its own table. Cannot write items. |

**Turn cap 8.** **Hooks:** host allowlist enforced at the hook, so a redirect off-domain is blocked rather than followed. Ingestion horizon enforced at the hook, so an out-of-window document is rejected before any fetch, not filtered afterward.

**Why it is a loop:** the site is inconsistent. Whether a row is a cancellation, a Spanish variant of something already held, or genuinely new depends on what it observes as it goes.

### Loop 2 — Extractor
**Job:** turn one changed document into items with page ranges. Invoked per document. This is the agent that touches untrusted content, so it is the most tightly clamped thing in the system.

| Tool | Does | Constraint |
| --- | --- | --- |
| `find_listing_pages(document_id)` | Locates the agenda's own table of contents | First action, always. |
| `get_document_pages(document_id, range)` | Text for a page range | Only the document it was invoked on. Hard page-count cap. |
| `extract_items(page_range)` | Structured item extraction | Schema-constrained. Rejected output never persists. |
| `record_items(...)` | Writes items | Its own table only. Cannot write documents, cannot write drafts. |

**No fetch. No shell. No network. No outward agent calls.**

**Turn cap 6.** Hard token cap. Both must demonstrably fire on an oversized packet, and that firing is a demo.

**Hooks:** tool allowlist, so an injected instruction to fetch a URL is blocked at the hook and logged as a NEVER-list trip. Page-range cap enforced, so "read the whole 312 pages" cannot happen. Output containing item numbers or page ranges absent from the source is rejected before storage.

**Why it is a loop:** find the listing pages, read them, decide which page ranges matter, fetch only those, validate, retry once on schema failure. The observation genuinely determines the next action, and this is the cost lever of the entire system.

**Downstream, outside the loop:** the rewrite. Single call, structured output, no tools, no turns. Then the six-check deterministic verifier (§4). The model does not grade itself. Whether that call goes through Strands or direct Converse is OPEN.

### Loop 3 — Watcher
**Job:** given one person's watchlist and what is new, decide what matters, explain why, assemble the draft scaffold.

| Tool | Does | Constraint |
| --- | --- | --- |
| `get_watchlist()` | The person's terms | Session-scoped. One person per invocation. |
| `get_new_items(since)` | Items added or changed since their last view | Read only. |
| `expand_terms(term)` | Vocabulary bridge lookup | Deterministic table. No model. |
| `get_item_detail(item_id)` | Full text of one item | Read only. The observation step. |
| `record_match(item_id, reason)` | Records a match with its plain-language reason | Reason is required. Cannot record a match without one. |
| `draft_scaffold(item_id)` | Builds letter structure with receipts | Structure only. No stance fields (§4b). |

**Turn cap 5.** **Hooks:** one watchlist per invocation, so cross-person reasoning is impossible by construction rather than by prompt. **No aggregation tools exist at all**, which is how the no-scorecard NEVER is enforced structurally. **No send tool exists in the codebase.**

**Why it is a loop:** relevance to "anything affecting the R-2 zone near Main Street" is not string matching, and deciding sometimes requires pulling the full item first.

**Error asymmetry, stated so it does not drift.** For a watcher, a false positive is mild annoyance and a false negative is a missed deadline. These are not symmetric. The watcher **errs toward showing.** Noise is controlled by the required explainability line, never by silence. Without this written down, tuning drifts toward looking clean at the cost of the exact harm the product exists to prevent.

### Directionality
Watcher may invoke Extractor. Extractor invokes nothing. Hunter invokes nothing. Wired as Agent-as-Tool, enforced at the hook layer, not by prompt. The whole security posture in one sentence: **the agent that touches untrusted content is the agent with the fewest tools.**

Caps firing is a demo, not just a safety net. Cap-fired messages surface in the run log and on screen.

### Cold start
First run, everything is new, so a naive watcher would produce a 700-item briefing and deliver the exact overwhelm the product exists to prevent. Same problem when someone adds a new term to an existing watchlist.

**Rule:** a backfill pass establishes the baseline silently. The first briefing is scoped and framed as a starting point, not an alert storm. A newly added watch term gets the same treatment: baseline first, alerts after. This is a Design criterion issue as much as a technical one.

---

## 4. The rewrite verifier (deterministic, external)

A **loop** is the model deciding to act again. A **retry** is deterministic code deciding, after checking output against source. The rewrite gets the second one. The model never grades its own output.

Every rewritten item passes a pure-code verifier:

1. **Structured output** — shape guaranteed before anything else runs.
2. **Entity preservation** — every number, date, dollar amount, street name, and proper noun in the output must be present in the source page range. Present, not similar.
3. **No new entities** — anything in the output absent from the source fails.
4. **Containment** — item number, page range, deadline, and body are never read from model output. They are attached deterministically from the extraction record.
5. **Reading level and length** — if it did not get simpler, it did not do its job.
6. **Both languages** — the Spanish rewrite passes the same entity check against the same source. This is how a translation that quietly changed a number gets caught.

Fail once, retry once with the failure reason. Fail twice, **mark the item unrewritten and show the original staff language with a note.** Never a fabricated summary.

Rejection counts go in the run log and on screen. "3 items could not be summarized reliably, showing original text" is a trust feature.

---

## 4b. The draft letter — structure, never stance

The riskiest output in the system. It goes out under a resident's name, into a public record, on a political question. It gets its own rules.

**The agent drafts structure. The human writes the position.**

The scaffold contains only: the item and what it is, the receipt (body, meeting date, item number, page range, PDF link), the meeting logistics, how and where comment is submitted, and the deadline in city local time. Then labeled blank fields the human fills: **your position**, **why this matters to you**, **what you are asking for**.

**Never generated by the model:** a position for or against, a recommendation, a persuasive argument, a claim about consequences, or a characterization of anyone's motives. A model deciding a citizen's political stance is the most severe Model Authority Check failure available in this build.

**Every factual element in the scaffold passes the §4 verifier.** Nothing in the letter that is not in the source.

**Injection ceiling, revised.** The original handoff doc said the worst case of a poisoned packet was one bad item summary. With a draft letter in the product that ceiling is higher: injected text could shape a public comment. Mitigations: the scaffold's factual fields are populated from the extraction record rather than from model output, the stance fields are empty by construction so there is nothing for injected text to steer, and the human reads before sending. The poisoned-PDF test (§11) must include a case that attempts to steer a draft, not only one that attempts a tool call.

**Voice.** Bulk AI-written comment letters actively degrade the public comment process, and clerks already fight this. A scaffold the human completes in their own words is the opposite of that, and it is the honest version of "the agent drafts, a human sends."

This is weaker as a demo and much stronger as a product.

---

## 5. Search path

The user types a sentence. Four stages, one model.

1. **The bridge** — deterministic lookup table, resident word to agenda vocabulary. "Bar" expands to conditional use permit, ABC license, on-sale general. "Pothole" expands to pavement management, resurfacing, capital improvement. Hand-maintained, versioned, inspectable. Cheapest quality lever in the system: one new row fixes a whole class of failed searches with no model involved. Concept carried from civiq, table rebuilt from scratch.
2. **Lexical search** over item text, bridge-expanded.
3. **Vector search** over item embeddings, for phrasings the bridge does not cover.
4. **Rank fusion.** Proven at this scale in civiq to beat either half alone.

**No agent in the search path.** Search is a pull, the watch is a push. Only the watch reasons.

**Vector store: Postgres + pgvector from day one.** Reversed an earlier call to use an in-process index. 707 items argues for in-process; Los Angeles does not, and portability outranks convenience in the decision criteria. Same code path at 707 items and 70,000.

---

## 6. Memory and storage

**The watchlist is data, not memory.** User-authored, explicit, editable, deletable, visible. Never model-inferred. A model deciding what you care about is a Model Authority Check failure and the creepiest available failure mode.

**Local storage, argued forward as a stance:** your watchlist never leaves your browser. We do not have it, cannot be subpoenaed for it, cannot be breached out of it. Also deletes the entire auth layer, which is the largest available scope cut.

**The draft queue lives in local storage too.** Server-side drafts would mean storing a named person's political intent, which is the single category of data this project should least want to hold. Keeping drafts local makes the privacy claim cover the whole product rather than half of it.

**Portability without a developer artifact.** No JSON export. A resident does not use JSON. Instead:
- **"Save this watch"** produces a link with the watchlist encoded in it. Bookmark it, email it to yourself, open it on another device. Nothing touches a server.
- A **plain readable list** of what you are watching, in words, copyable and printable. If everything breaks, a human can rebuild it by hand.
- A plain-language on-screen warning that this lives on this device and in that link, and we do not have a copy.

**The watchlist goes in the URL fragment, after the `#`. Never in a query string.** Fragments are never transmitted to the server. A query string would land in server access logs and in Referer headers on every outbound click, which would make the privacy claim false. Paired with `Referrer-Policy: no-referrer`.

**Limitations language, stated plainly on screen** (honest over optimistic): the link is exactly as private as wherever you put it. Emailing it to yourself means your email provider has it. Browser sync means your browser vendor has it. We still do not.

**AgentCore Memory, split:**
- Short-term / session memory: **MUST.** The agent's working context across tool calls within a run. Native, cheap, honest.
- Long-term semantic / preference memory: **STUB for v2**, with the stub comment stating the reason: model-extracted preferences would give a model authority over what the user cares about, and this product does not do that.

---

## 7. Guardrails from civiq

The prototype earned these. All are lessons, not code.

**Fail closed, always.** civiq's known defect: when the embedding provider was unavailable, the dense floor safety mechanism failed and fabricated queries returned false results. It failed *open*. New rule: every degradation fails closed. If a dependency is down, the honest empty state is the answer. "We could not search reliably just now" is always correct. A result we cannot stand behind never renders.

**Stale agenda guardrail.** civiq fetched old agendas. Two separate rules, and conflating them is what caused it:
- **Ingestion horizon** — do not fetch documents for meetings outside a defined window. Computed from the *meeting* date, never the posting date, never the file name.
- **Surfacing rule** — posting order is not chronology. An agenda amended two weeks after its meeting (a real case found on the Ventura site) is genuinely new material for a meeting that already happened. It gets ingested and recorded. It never appears as upcoming. Both rules get tests built from real documents on the live site.

**Good-citizen posture** (carried from the handoff doc, where it was nearly lost). Respect robots.txt. Descriptive user agent naming the project with a contact URL. Conditional GET. Hourly, not continuous. Exponential backoff. **Read the city's terms of use before Block 1, not after.** This is both the right thing to do and the thing that stops us getting blocked at a bad moment.

**Run lock and idempotency.** The schedule is hourly and a slow run can overlap itself, so a run lock is required. A run that crashes partway and restarts must not double-write. Content-hash document ids get most of the way there, but idempotency is stated as a guarantee with a test, not inferred from the id scheme.

**Proven and carried forward:** corpus is small (21 bodies, 141 agendas, 707 items). Hybrid retrieval with rank fusion beats either half. Honest empty states work. Zero model-generated citations works. Document role classification already identifies Spanish editions and links rather than duplicates them, so the hard half of bilingual is solved and the remaining work is authoring.

---

## 8. Bilingual — MUST

Spanish is a first-class surface, not a translate button. Item summaries and UI chrome, not full packets.

- NEVER list holds in both languages. Dates, deadlines, item numbers, page ranges are copied, never generated, never translated into ambiguity.
- Spanish rewrites pass the same deterministic entity verifier as English.
- Quality gate: native-fluency spot check on a fixed sample, documented. Failure path is showing the original source, never shipping an uncertain translation. **OPEN: who performs the check.** If no fluent reviewer is available, the honest move is to say so in the README and treat the Spanish surface as unverified rather than claim a review that did not happen.
- `lang` attributes correct on language-switched regions. This is where bilingual pages usually fail accessibility.
- Language choice persists.
- When the city posts the Spanish agenda late or not at all, existing phrasing handles it without judgment: "not located at [url] as of [timestamp]."

---

## 9. Accessibility — WCAG 2.1 AA, MUST

Full keyboard operability tested with the mouse unused. Screen reader pass start to finish without looking at the screen. `lang` correct on both language surfaces. Heading order, landmarks. `prefers-reduced-motion`. 44px touch targets. 320px with no horizontal scroll. Contrast computed and recorded, as in the v0.4 mock. **Demo video captioned** — an uncaptioned video claiming accessibility is a gift to a judge.

**Failure states must be accessible.** `aria-live` on every status and error region. An error that renders visually but is never announced fails a screen reader user at exactly the moment they need the information. Every state in the §16b table gets this treatment, including the restful "nothing happened" one.

---

## 10. MUST / STUB / NEVER

**MUST:** CivicPlus vendor adapter with all edge cases (cancellations, amended, supplemental, Spanish variants). Hash-based change detection. Two-pass extraction with page ranges and hard caps that demonstrably fire. Deterministic rewrite verifier. Draft scaffold with no stance fields. Timezone-explicit deadline handling. Cold-start baseline pass. Run lock and idempotency guarantee. Good-citizen fetch posture. `aria-live` on all failure states. Public reading log. Clean-clone setup with a seeded sample dataset. Receipts on everything. Three agent loops with scoped tools. Hooks enforcing the NEVER list at runtime. Watch loop with per-person relevance **and a visible plain-language reason for every match**. Draft queue with human confirm. Bilingual output. pgvector. Vocabulary bridge. Application-level spend ledger checked before every run. Fail-closed degradation. Ingestion horizon and surfacing rules. Prompt injection containment, demonstrated. WCAG 2.1 AA. Honest dormancy. Deployed on AgentCore with a live link.

**STUB (comment plus implementation note, never half-built):** multi-city fan-out. OCR for image-only packets (the honest path ships: mark unparsed with a reason, show the link). Historical pulls behind the JavaScript year navigation. Accounts and auth. Email or SMS delivery of the briefing. The PreviousVersions endpoint as a change-detection source. Long-term semantic memory. Hosted error tracking, HA, full CI/CD.

**NEVER (behavior; a future stub is fine, the behavior is not):**
- No scores, grades, rankings, or per-body sums. Aggregation is the mechanism that turns this into a harassment tool, so the mechanism is never built.
- No model-generated dates, deadlines, item numbers, or page ranges.
- Never send to a government office. No send capability anywhere, including in stubs.
- Never show anything without a receipt: body, date, item number, page range, link.
- Never assert absence. "Not located at [url] as of [timestamp]."
- Never let packet text act as instruction.
- **Never build a shared or public watchlist.** Visible watchlists tell you who is tracking what, which is a surveillance surface pointed at neighbors and organizers. Private to the device, full stop.
- Never fail open.
- No `innerHTML`, no `eval`, no key on the client, no god files, no silently swallowed failures.

---

## 11. Judge-facing additions (low risk, high reward)

Ranked. Confirmed in.

1. **Enforce the NEVER list in code with Strands hooks.** Scoped tools blocked at the hook, not the prompt. Model output containing a date or page range in a copied-from-source field rejected before storage. Converts the ethics from a document into a runtime control. Top recommendation.
2. **A poisoned PDF in the repo with a passing containment test.** Adversarial testing that is honest rather than theatrical, because we genuinely read untrusted documents from servers we do not control.
3. **A golden set and a published accuracy number.** ~20 items extracted by hand from real packets, checked by eye. AgentCore CLI has evaluators built in. The reward is not the number, it is having measured. A bad number honestly reported is still a good README.
4. **Reasoning trace in the UI**, in plain language. Strands ships observability with trace attributes. A receipt for the reasoning next to the receipt for the source.
5. **Show the money.** "This run read 3 packets, 412 pages, cost $0.11."
6. **Captioned video and correct `lang`.**
7. **PreviousVersions endpoint** for deterministic version diffs. Gated on Block 2 going smoothly.
8. **MCP server over the record.** Real creativity payoff, ranked last because it could quietly eat two days.

**Skipped deliberately:** multi-city (dilutes Design), email/SMS delivery (looks like the agent sending things, which muddies the exact line we are being deliberate about).

**9. Judges must be able to run it.** Setup instructions verified from a clean clone, plus a **seeded sample dataset** so the repo demos without AWS credentials. A judge who cannot run it scores Technical Implementation from the video alone. Cheap, and almost nobody does it.

### Maintenance rules for the two things that will rot
- **The golden set** goes stale as the city's site changes. Refresh trigger: any adapter change, or a failed run attributable to a site change. Otherwise it silently measures a world that no longer exists.
- **The vocabulary bridge** is the cheapest quality lever in the system and will otherwise be filled once and abandoned. It needs a named owner (Shara) and a standing process: every failed or empty search that should have matched becomes a candidate row. Versioned, reviewed, never model-generated.

---

## 12. User-facing additions (low risk, high reward)

1. **Jump straight to the page.** PDF opens at page 118, not page 1. A URL fragment. Twenty minutes.
2. **Deadlines in human time.** "Closes tomorrow at 5." Copied from source, rendered relative.
3. **Scale honesty.** "This packet is 312 pages. Your item is 12 of them."
4. **One tap from a search result to a watch.** The conversion moment. One button, no account.
5. **A real "nothing happened" state.** Most weeks nothing on your street happens and the tool should say so restfully. Everything else in this space is built to make you feel behind. Fight for this one.
6. **Share one item, never a watchlist.** Public record is safe to share. The watchlist is not.
7. **Language choice sticks,** and the Spanish page is a real page.

---

## 13. Wind-down

Two things, both required.

**Product: honest dormancy, built from the start.** If the pipeline stops, the site must not keep showing an August calendar as if it were current. Past a threshold the site states plainly that it stopped reading on this date and points to the city's own page. No 404, no stale confidence. Roughly three hours of work, and it is a Design criterion point because almost nobody designs the failure state of their own attention.

**Personal: Block 7 is Wind Down, written on day one, not at the end.**
- What happens on Oct 15, the day after winners are announced. Decided now, not then: keep running, park read-only, or take down.
- The monthly dollar ceiling past which it goes dormant automatically, not by a decision made in the moment.
- A handoff note to future Shara: what it does, what is stubbed and why, what would make it worth picking up, what would not.
- Final entry appended to WINS.md, honestly, including if it does not place.

Rationale: the standing rule is to shelve projects when enthusiasm is absent. The missing piece is a mechanism, so shelving reads as abandonment instead of a completed step.

---

## 14. Build notes for Kiro

**Method:** spec-driven development in Kiro. Spec, design, tasks maps onto the block structure. Staged prompts: propose, Shara approves, then implement. Explicit "DO NOT refactor other code" guardrails on every prompt.

**Language:** Python.

**Agent framework:** Strands Agents SDK. Pin the exact version at build start and record it here. ReAct via the native agent loop.

### Agent Toolkit for AWS
**https://aws.amazon.com/products/developer-tools/agent-toolkit-for-aws/**
Repo: https://github.com/aws/agent-toolkit-for-aws

GA, no additional charge, pay only for provisioned resources. Setup: `aws configure agent-toolkit`. Kiro is a first-class target.

Four parts:
- **AWS MCP Server** (managed remote): secure agent access to 300+ services, sandboxed Python execution, live docs, CloudWatch and IAM controls.
- **Agent Skills**: 20+ curated instruction packages, load on demand.
- **Agent Plugins**: install bundles for Kiro, Claude Code, Cursor, Codex.
- **Rule Files**: persistent project-level instructions per session.

**Use it for:** the infrastructure layers. Hosting, deployment, cloud/compute, CI/CD, IAM, logging, alarms. This is where a solo builder loses days.

**Do not:** put it in the architecture diagram or count it toward "thorough use of Strands Agents." It is a build-time tool, not a runtime dependency of the product.

**Gotcha:** the 20+ skills often never load unless the rule file is present. Add it day one.
Reference: https://dev.to/aws/the-new-agent-toolkit-for-aws-includes-20-agent-skills-but-your-agent-might-never-load-them-1p6d
Setup walkthrough: https://dev.to/raabdahl/setting-up-the-agent-toolkit-for-aws-in-kiro-and-codex-claude-code-and-cursor-2amm

### Deployment tooling — LONGEVITY FLAG
The hackathon Resources page links **`bedrock-agentcore-starter-toolkit`** (Python, pip). The AWS repo for it now marks it **legacy** and directs new projects to the **AgentCore CLI** (`npm install -g @aws/agentcore`, v0.14.1, May 2026). Both install the same `agentcore` command, so they conflict — uninstall one.

**Decision: use the AgentCore CLI.** It supports Strands as a first-class framework (Python and TypeScript, AWS-native streaming), and ships a local dev server, infra deploy, memory and credential management, log and trace inspection, and evaluators (which feed the golden-set item above).

---

## 15. Open items

- Rewrite call path: Strands single call vs direct Converse API. The rewrite has no tools and no loop, which is the argument for direct Converse. Decide before Block 3.
- Strands SDK version not pinned.
- Embedding provider not chosen. Must fail closed when unavailable (see §7).
- UI direction not chosen. Current v0.4 mock is being discarded as a direction, not iterated. Brief: **it is a stakeout, not a record.** Somebody read all 312 pages so you did not have to and is leaning over to tell you the one thing that matters. Serious enough for trust, with personality. Keep high contrast, real editorial typography, visible receipts. Drop the paper ground, muted palette, dotted-underline restraint, section numerals, and the broadsheet posture. Two or three real mocks to follow.
- Ingestion horizon window length not set.
- AWS Builder ID not confirmed. Devpost registration not confirmed. $50 credits form not submitted (deadline Sep 11, 12:00 PM PT — submit in week one).
- Spike B (trivial Strands agent deployed to AgentCore) not run. Runs in week one.

---

## Changelog

**Aug 16, 2026.** Doc created. Persona moved from once-a-year resident to weekly watcher. Ventura only, bilingual MUST, Python confirmed. Vector store call reversed to pgvector on portability grounds (Los Angeles scale-out). Rewrite verifier specified as deterministic and external after the "where is the check that the output is correct" catch — the model does not grade its own output. Stale-agenda guardrail split into ingestion horizon and surfacing rule after the civiq old-agenda failure. Fail-closed rule adopted from the civiq dense-floor defect. Match explainability confirmed MUST. Agent Toolkit for AWS added to Kiro build notes. AgentCore CLI chosen over the legacy starter toolkit the hackathon Resources page links.

---

## 16. Retry policy and failure states

### 16a. Retry budget, five layers

Turn caps (§3) govern a single invocation. These sit above them.

**Layer 1 — attempts per document per stage: two.** First attempt, then one retry with the failure reason attached. Exponential backoff between. After two, the document is parked with a status and a reason. Never a third.

**Layer 2 — transient vs permanent.** This classification decides whether it ever tries again, and it is the layer that prevents an hourly loop grinding against the same broken document for a month.
- **Transient** (timeout, 5xx from the city, rate limit, embedding provider unavailable): parked, **automatically retried next run.** No human involved.
- **Permanent** (image-only scan with no text layer, schema validation failed twice, malformed PDF): parked, **never retried automatically.** Retrying hourly burns money to fail identically. Clearing it requires a code change or an OCR path, both human decisions.

**Layer 3 — run circuit breaker.** If more than a threshold of documents in a single run fail, stop the run. Something changed on the city's side and continuing spends money to be wrong at scale. Log, surface, wait for the next run.

**Layer 4 — consecutive-run quarantine.** If one body fails three runs in a row, quarantine that body. Stop attempting it, keep serving what is already held for it, mark it plainly. This is what stops a site redesign from becoming a week of silent failure and a surprise bill.

**Layer 5 — spend ceiling.** Application level, checked before every run (never a cloud budget alert, which only sends email). When the envelope is spent the run does not start. Backstop for whatever the other four missed.

Separately, and not a retry policy: politeness backoff on 429 or 503 from the city server. Obligation, not optimization.

### 16a-ii. Thresholds — every one needs a number before Block 2

All currently unset. Each gets a value **and a one-line rationale**, so future Shara knows whether it was reasoned or guessed. Guessed is acceptable; unlabeled is not.

| Threshold | Value | Rationale |
| --- | --- | --- |
| Attempts per document per stage | 2 | Set. One retry, then park. |
| Hunter / Extractor / Watcher turn caps | 8 / 6 / 5 | Set, provisional. Revisit after Block 3 with real traces. |
| Circuit breaker: run failure percentage | OPEN | |
| Quarantine: consecutive failed runs per body | OPEN (3 proposed) | Proposed by Claude, not yet ruled on. |
| Ingestion horizon window | OPEN | |
| Dormancy threshold (days since last successful run) | OPEN | |
| Monthly spend ceiling | OPEN | Also the §13 auto-dormancy trigger. |
| Search rate limit | OPEN | |
| Draft rate limit | OPEN | |
| Extractor page-count cap | OPEN | |

### 16b. User-facing failure paths

**Governing principle: never ask the user to retry something they have no power over.** A retry button on the ingestion pipeline is a lie with a cursor on it. The user cannot make the city's server respond.

Every failure state ends at the same escape hatch: **a link to the city's own page.** That is the floor. The worst thing this tool can do is leave someone with nothing, and the city page always exists.

| Failure | What the user sees | Retry offered |
| --- | --- | --- |
| Item could not be summarized | Original staff language with a note. Receipt, page range, and PDF link all still correct. Degraded, not broken. | No. Nothing to retry. |
| Document could not be read (scanned) | "We could not read this one," plus the PDF link. | No. |
| A body was not read this run | Per-body last-read timestamps, never one global timestamp. "Planning Commission, read 2 hours ago. Parks and Recreation, read 3 days ago." | No. |
| Search unavailable | Fail closed. Honest empty state, never fabricated results. "Search is not working reliably right now," plus the city's own search page. Never an unresolving spinner, never a blank screen. | Yes, bounded. |
| The watch has not run | Dormancy language on a shorter clock. "We last read the city on [date]." Escalates to the full dormancy notice past threshold. | No. |
| Nothing found | Not a failure. The restful state. Say so plainly. | No. |
| Draft could not be generated | The item and its receipt remain. | Yes, bounded. |
| Partial stream death (tenth state) | Agent response stream died partway through, leaving a partial answer that looks complete. Noted-not-built, Spec 5. §31. | No. (Detection + honest truncation marker needed.) |
| Extractor egress question | §30d: PUBLIC networkMode allows outbound egress. Extractor must have no network egress (§19). VPC networkMode with no egress route, or the claim must be downgraded. Noted-not-built, Spec 5 decision. | N/A. |
| Partially-read document (eleventh state) | The extractor cap fired mid-agenda. Items extracted before the cap are shown (real, verifiable); the document is marked "partially read" with the reason and the source link so the reader opens the PDF for the rest. Never partial-shown-as-complete. Spec 3, R1.7. | No. (Open the city PDF.) |

**The only two user-facing retries are re-run a search and re-draft a comment.** Both cheap, both rate limited, both things the user actually controls. Nothing else gets a button.

A single global last-read timestamp is banned. It hides exactly the failure a watcher needs to see.

### 16c. Public reading log — MUST

The readlog already exists in the data model. Render it publicly: what was read, when, what was skipped because nothing changed, what failed and why, what is quarantined, what each run cost.

For the watcher persona this is the trust artifact. Without it, "the tool is quiet because nothing happened" and "the tool is quiet because it broke three days ago" are indistinguishable, and the second one costs someone a deadline. It is also the thesis again: invisible system health made inspectable.

Low cost. The data exists. It is a rendering.

---

## 17. Observability, logging, and identifiers

Requirement: any failure a user sees on screen must be traceable to a specific run in the AWS console within about a minute, without guessing.

### 17a. The correlation identifier

**`run_id` is generated once per pipeline run and propagated everywhere.** Every log line, every database row written during that run, every trace, every cost ledger entry, and every user-visible status.

Format: sortable and time-prefixed, `run_YYYYMMDDTHHMMSSZ_<short random>`. Sortable means the console search is chronological for free.

Child identifiers, all carrying the parent `run_id`: `body_id` (stable, from the adapter), `document_id` (content hash based, so the same PDF is always the same id), `item_id`, `agent_invocation_id` (per loop invocation, so hunter, extractor, and watcher are separable within one run).

**The run_id is shown in the UI.** On the public reading log per run, and in the detail of any failure state. That is what closes the loop: a user reports "it says it could not read the Planning Commission packet," they give you the run id, and you go straight to it.

### 17b. Naming and tagging, so the console is navigable

Every provisioned resource follows one convention: **`agendawatch-<env>-<component>`**. Env is `dev` or `prod`. Component is `hunter`, `extractor`, `watcher`, `web`, `db`, `queue`.

Every resource carries the same tag set, no exceptions:
- `Project = AgendaWatch`
- `Env = dev | prod`
- `Owner = shara`
- `Purpose = hackathon-agents-for-humans`

Cost allocation tags activated on day one, not after the first surprising bill. This is what makes per-component spend readable in Cost Explorer and it is retroactively impossible.

**CloudWatch log groups:** `/agendawatch/<env>/<component>`. One per component, predictable, so there is never a hunt.

### 17c. What gets logged

Structured JSON, one event per line, `run_id` on every line. No print statements, no unstructured strings.

Every log event carries: timestamp, `run_id`, component, level, event type, and the relevant child ids.

Events that must be logged: run start and end with duration and cost. Every document seen, with the change-detection outcome (unchanged and skipped counts as an event, because "we spent nothing" is a claim we make publicly and it needs evidence). Every agent invocation with turn count and whether a cap fired. Every retry with attempt number and classification. Every parked document with reason and transient/permanent. Every verifier rejection with which check failed. Every quarantine and circuit-breaker trip. Every hook block, meaning the NEVER list firing at runtime.

**Persistent failure log** (`logs/failures.log`, carried from the standing pattern): written from every catch and every degrade. Nothing is swallowed silently, ever.

### 17d. Tracing

Strands ships observability with trace attributes, and the AgentCore CLI provides log and trace inspection. Wire OpenTelemetry through to CloudWatch and X-Ray so agent turns are inspectable as spans, not just as text.

Span attributes must include `run_id`, loop name, turn number, tool called, and whether a cap or hook fired. The reasoning trace surfaced in the UI (§11, item 4) reads from this same instrumentation. One source, two audiences.

### 17e. Alarms

Minimum viable, because full alerting is a STUB:
- Spend ledger crosses the warning threshold.
- Circuit breaker trips.
- Any body enters quarantine.
- Zero successful runs in a defined window (the failure that is otherwise silent by nature).

### 17f. Checks

- A health endpoint reporting last successful run, per-body last-read times, and quarantine state. Feeds the public reading log rather than duplicating it.
- Golden-set accuracy run (§11, item 3) executed on demand and its result recorded with a `run_id` like anything else.
- Pre-deploy: verify no key is in the repo or in git history, verify log output contains no packet content beyond what is already public, verify `run_id` propagation end to end on one real run.

---

## Changelog (continued)

**Aug 16, 2026 (second pass).** Added §16 retry policy (five layers, transient/permanent split, circuit breaker, quarantine), user-facing failure paths with the "never offer a retry the user has no power over" principle and the city-page escape hatch, public reading log promoted to MUST, and §17 observability with `run_id` correlation, resource naming and tagging conventions, log group structure, structured logging event list, tracing, alarms, and checks. Single global last-read timestamp explicitly banned.

**Aug 16, 2026 (third pass — QA findings worked in place).** Adversarial QA of the hardening produced twelve findings, all accepted and folded into their relevant sections rather than appended as a separate list.

- §2: model gains a third job (draft structure), gains an explicit political-position prohibition, and time is declared deterministic with city-local rendering and a DST test case.
- §3: expanded from a summary into the full agent surface map — tools per loop, constraints per tool, hooks per loop, directionality, error asymmetry (watcher errs toward showing), and the cold-start baseline rule.
- §4b: new. The draft letter gets structure-never-stance, its own verifier pass, and a revised injection ceiling. The poisoned-PDF test must now include a draft-steering case, not only a tool-call case.
- §6: watchlist moves to the URL fragment (query strings would leak via access logs and Referer, making the privacy claim false), `Referrer-Policy: no-referrer`, limitations language on screen, and the draft queue moves to local storage so the privacy claim covers the whole product.
- §7: good-citizen fetch posture restored from the handoff doc, city terms of use to be read before Block 1, run lock and idempotency guarantee added.
- §8: Spanish reviewer flagged OPEN, with the honest fallback of declaring the surface unverified.
- §9: `aria-live` required on all failure states.
- §10: MUST list extended.
- §11: judge-runnable clean clone with seeded sample data added; maintenance rules written for the golden set and the vocabulary bridge, the two things that will otherwise rot.
- §16: threshold table added. Ten values, two set, eight OPEN, each requiring a rationale before Block 2.

Rulings taken this pass: draft letter is structure-never-stance (Claude's recommendation, accepted); all twelve findings worked in place rather than appended.

---

## 18. Full-stack production reality — all 13 layers, declared

This is a **prototype**, and the honest move is to say which layers are real, which are deliberately thin, and why. A hackathon build that claims production maturity it does not have is overclaiming. A hackathon build that shows it knows all 13 layers and made deliberate cuts reads as production maturity to a judge, which most demos cannot claim.

Rating scale: **MUST** (built, real), **LITE** (built, minimal, honest about it), **STUB** (comment stub with implementation notes, not built), **N/A** (does not exist in this architecture, and that is a design outcome).

| # | Layer | Call | Why |
| --- | --- | --- | --- |
| 1 | **Frontend** | MUST | Judged on Design and Presentation. Bilingual, WCAG 2.1 AA, all failure states from §16b with `aria-live`. |
| 2 | **APIs & backend logic** | MUST | Three services: ingestion, extraction, web/search. The seam between pipeline and site is the database, deliberately. If the pipeline breaks the site keeps serving with an honest last-read timestamp. |
| 3 | **Database & storage** | MUST | Postgres + pgvector. Meetings, documents, items, events, readlog, budget. Simple access patterns, few writes, cheap reads. |
| 4 | **Auth & permissions** | **N/A, by design** | There are no accounts. Watchlist and draft queue live in the browser (§6). This is the largest scope cut in the build and it is also a privacy property, not just a shortcut. Admin/ingestion endpoints are not public. |
| 5 | **Hosting & deployment** | MUST | AgentCore for the agents via the AgentCore CLI. Live demo link is explicitly worth score. Infrastructure built with the Agent Toolkit for AWS. |
| 6 | **Cloud & compute** | MUST | Scale to zero between runs. The pipeline is idle roughly 95% of the time and paying for idle is the fastest way to lose the budget. |
| 7 | **CI/CD & version control** | **LITE** | Git from commit one, and the commit history is also the compliance artifact: dates after Aug 10 are the evidence for the "newly created" rule. CI is one GitHub Actions workflow running tests plus the golden set. No CD, no environments, no branch protection. Solo build, 29 days. |
| 8 | **Security & RLS** | MUST (RLS **N/A**) | Full sweep in §18b. Row-level security is N/A because no user rows exist to scope. Everything else is real. |
| 9 | **Rate limiting** | **MUST, and upgraded in priority** | See §18b finding. Not a nice-to-have here. |
| 10 | **Caching & CDN** | LITE | Host CDN serves static assets. Query-embedding cache is required for the §18b cost issue, not for speed. No response caching beyond that. |
| 11 | **Load balancing & scaling** | STUB | Serverless host auto-scales. No custom balancing at demo scale. Note as v2. |
| 12 | **Error tracking & logs** | MUST | §17 in full: structured JSON, `run_id` on every line, per-component CloudWatch log groups, persistent failure log, OTEL traces to CloudWatch and X-Ray, four alarms. Hosted error tracking (Sentry) is STUB. |
| 13 | **Availability & recovery** | LITE | Rollback is redeploy the previous build, documented before launch. **Recovery has an unusual property worth stating: the city is the source of truth.** If the database is lost, it is rebuilt by re-running ingestion. No backup restore path is required for correctness, only for cost. No HA. |

**This table is also a slide.** It goes in the architecture section of the README and it is worth thirty seconds of the demo video.

---

## 18b. Security sweep, final pass

### FINDING: the public search endpoint is a cost-drain vector

Every search embeds the query, and every embedding call costs money. The search endpoint is public, unauthenticated by design, and there is no account to throttle against. An attacker, or a badly behaved crawler, can hammer it and drain the month's budget in an afternoon. The spend ledger would correctly halt the pipeline, which means **an attacker could take the watch offline by spamming search.** Availability attack via the cost path.

Three mitigations, all required together:
1. **Rate limiting per IP on search.** This is why layer 9 is a MUST rather than a lite.
2. **Cache query embeddings.** Repeated and common queries cost nothing after the first. This is also a straightforward speed win.
3. **A separate search spend sub-budget** so search exhaustion cannot starve ingestion. The pipeline's envelope and the public endpoint's envelope are not the same pool.

This was not in any prior section. It is the one real gap the 13-layer pass turned up.

### The 11-point checklist, resolved against this build

1. **Authorization** — no user accounts (layer 4, N/A). Ingestion and admin endpoints not publicly reachable. Only the read-only search endpoint and the site are public.
2. **Input validation and sanitization** — client side and server side, never trusting the front end. Search queries and watchlist terms: length caps, term-count caps, character validation. Shared-link watchlists validated and **confirmed by the user before applying** (see the Kiro plan for the shared-link injection vector).
3. **CORS** — configured to the site's own origin. Never wildcarded.
4. **Rate limiting** — search, draft generation, and any agent-triggering path. See the finding above.
5. **Secrets** — server side only, in Secrets Manager or `process.env`. Never on the client, never in the repo. **Repo history scanned before it goes public**, not just the working tree.
6. **Frontend error handling** — `try/catch` on every fetch. Meaningful error states, never a blank screen, never an unresolving spinner. Every state announced via `aria-live` (§9).
7. **Database indexes** — on the query paths that matter: document hash, meeting date, body, and the vector index.
8. **Logging** — §17 in full. Nothing swallowed silently.
9. **Alarms** — spend threshold, circuit breaker trip, body quarantine, zero successful runs in a window.
10. **Rollback plan** — documented before launch. Redeploy previous build. Data is re-ingestible from the city (layer 13).
11. **Prompt injection protection** — the deepest layer in this build. Extraction tools scoped at the hook, not the prompt. Packet text treated as data, never instruction. Schema-constrained output. Bedrock Guardrails prompt-attack filter as a second layer. A poisoned PDF committed to the repo with a passing containment test, including a case that attempts to steer a draft.

### Additions beyond the 11 points

- **SSRF containment.** The hunter fetches URLs, so the host allowlist is enforced at the hook and off-domain redirects are blocked rather than followed. Without this, a manipulated listing page could point the fetcher anywhere.
- **Supply chain.** Lockfile committed, versions pinned, one dependency audit before submission. No automated dependency bots, which are noise in a 29-day window. The standing tool longevity check (verify nothing is deprecated or EOL) already caught the legacy AgentCore starter toolkit.
- **PII in the log path — OPEN.** Agenda packets contain applicant names and addresses. Public record, but "public inside a 300-page PDF" and "indexed, searchable, and sitting in our logs" are different exposures. Decide before Spec 3 whether logs carry packet text at all. Default position: they should not.
- **No client-side keys, no `innerHTML`, no `eval`, no browser storage beyond the watchlist and draft queue.**

---

## Changelog (continued)

**Aug 16, 2026 (fourth pass — full-stack reality check).** Added §18 declaring all 13 production layers as MUST / LITE / STUB / N/A with rationale, and §18b a final security sweep.

New in this pass:
- **Finding: the public search endpoint is a cost-drain and availability vector.** Unauthenticated by design, and every query costs an embedding call, so spam can exhaust the budget and take the watch offline through the spend ledger. Rate limiting upgraded to MUST, query-embedding cache required, and search given its own spend sub-budget separate from the pipeline's.
- Auth and RLS declared **N/A by design** rather than skipped, since the local-storage watchlist removes the user-row concept entirely.
- CI/CD declared LITE, with the note that **git history is also the compliance artifact** for the hackathon's "newly created" rule.
- Recovery property recorded: the city is the source of truth, so a lost database is rebuilt by re-running ingestion. Backups matter for cost, not correctness.
- SSRF containment and supply-chain posture added.
- PII in the log path carried forward as OPEN, to be decided before Spec 3. Default position: logs do not carry packet text.

---

## 19. AgentCore capability sweep

Run against the Strands + AgentCore curriculum topics. Every capability gets a call, so nothing is skipped by accident. **Verify Gateway and Identity behavior against current AWS docs before Spec 0** — the calls below reflect their documented purpose as of Aug 2026, not hands-on use.

| Capability | Call | Where |
| --- | --- | --- |
| Strands SDK + AgentCore Runtime | MUST | Spec 0. The whole build. |
| Extending agents with tools | MUST | §3. Fifteen tools across three loops. |
| Function calling | MUST | §3. The mechanism underneath every tool. |
| Structured outputs | MUST | Extractor schema, rewrite schema, match records. Verifier check 1 (§4). |
| Structured outputs with Strands + AgentCore | MUST | Same, implemented natively rather than hand-parsed. |
| Short-term agent memory | MUST | §6. Working context across tool calls within one invocation. |
| Long-term / semantic memory | STUB (v2) | §6, with a stated ethical reason. |
| External tools and APIs | MUST | The city's site, the model provider, the embedding provider. |
| **Agent state management** | **MUST, with a deliberate limit** | See §19a. |
| **AgentCore Gateway** | **NO** | See §19b. |
| **AgentCore Identity** | **Split: N/A for delegated access, MUST for execution role** | See §19c. |
| Observability and tracing | MUST | §17d. |

### 19a. Agent state — the unit of recovery is the document

State and memory are not the same thing and the docs have been treating them as one. Memory is what the agent knows. **State is where it is in a job**, and this build needs an explicit position on what happens when a run dies mid-document.

**Decision: agent state is not persisted across crashes. The unit of recovery is the whole document.**

If the extractor dies on page 140 of a 312-page packet, the document goes back to the queue and is re-extracted from the beginning on the next run. No checkpoint, no resume, no partially-written item set.

Rationale: documents are cheap to redo (a single packet is cents, and the two-pass approach means we re-read only the listing pages plus the target ranges), while partial-state resume is a whole class of correctness bugs — half-written item sets, duplicated items, page ranges attributed to the wrong pass. Idempotency is easy to guarantee at document granularity and hard to guarantee at turn granularity. Simplicity here is a correctness feature, not a shortcut.

This pairs with the run lock and content-hash ids in §7: re-running a document produces the same ids, so a redo overwrites rather than duplicates.

**Within** a single invocation, state is the agent's working context and is handled natively (short-term memory). Across invocations, there is no agent state at all — only database rows and the run log.

### 19b. AgentCore Gateway — no, and the reason matters

Gateway turns external APIs, Lambda functions, and services into MCP-compatible tools with managed authentication. It solves a real problem: many external services, each with its own auth, needing to become agent tools safely.

**We do not have that problem.** All fifteen tools are internal Python functions operating on our own database and one allowlisted public website. There is no third-party API requiring delegated credentials. Adding Gateway would insert a dependency and a network hop to solve a problem this architecture does not have, and it would weaken the thing that makes the security posture legible: **the extractor's tools are local functions with no network access at all.** Routing them through a gateway makes that harder to prove, not easier.

**The one scenario that would change this:** if the MCP server idea (§11, item 8) gets built, Gateway becomes the natural way to expose the agenda record as MCP tools with managed auth. That item is ranked last and gated. If it moves up, revisit this line.

Recorded as a deliberate no, not an oversight. Worth one sentence in the video, because "we evaluated it and did not need it" is a stronger technical signal than using every service on the menu.

### 19c. AgentCore Identity — split decision

Two different things wear this name and they get different answers.

**Delegated user identity: N/A, and this follows from §18 layer 4.** Identity exists so an agent can act on behalf of a user against third-party services, typically via OAuth. This product has no user accounts, no third-party services acting on a user's behalf, and no send capability. There is no delegation to secure because nothing is delegated. This is a design outcome of the local-storage watchlist, not a gap.

**Agent execution identity: MUST.** Each of the three agents runs under its own least-privilege IAM role, and the roles are not interchangeable:

- **Hunter** — read/write on the documents table, network egress restricted to the allowlisted host. No access to the items table.
- **Extractor** — read on documents, write on items, **no network egress at all**. This is the agent that reads untrusted content, and its IAM role should make the hook-level restrictions redundant rather than load-bearing. Two independent layers saying no.
- **Watcher** — read on items, write on matches. No write to documents. No egress.

Three roles, not one shared role. A single shared role would make the tool scoping in §3 a prompt-and-hook promise rather than an infrastructure fact. **Defense in depth means the IAM policy alone should stop what the hook alone already stops.**

Secrets accessed through Secrets Manager per role, never a shared credential.

---

## Changelog (continued)

**Aug 16, 2026 (fifth pass — AgentCore capability sweep).** Added §19, every AgentCore capability given an explicit call. Ten were already covered; three needed real decisions.

- **§19a Agent state:** separated state from memory, which had been conflated. Decision: no cross-crash state persistence. The unit of recovery is the whole document, because documents are cheap to redo and partial-state resume is a class of correctness bugs. Idempotency is guaranteeable at document granularity, not turn granularity.
- **§19b Gateway: deliberate no.** All tools are internal functions on our own data plus one allowlisted site. No third-party delegated auth exists to manage. Adding it would obscure the strongest security property in the build: the extractor has no network access. Revisit only if the MCP server item moves up.
- **§19c Identity: split.** Delegated user identity is N/A (follows from having no accounts). Agent execution identity is MUST, and upgraded: **three separate least-privilege IAM roles, not one.** The extractor's role carries no network egress, so IAM alone stops what the hooks alone already stop. Defense in depth by construction.

---

## 20. Runtime and orchestration hardening

§16 covers retries, §17 covers observability, §19c covers execution identity. None of them cover the layer that actually runs the agents. This section does.

### FINDING: the run lock can deadlock the entire system

§7 requires a run lock so an hourly schedule cannot overlap itself. But nothing in the docs sets a timeout on anything. Combine those two facts and you get the worst available failure mode:

A fetch hangs. The run never completes. The lock is never released. **Every subsequent run is blocked forever, silently.** The watch stops. No alarm fires, because "zero successful runs in a window" is the only alarm that would catch it, and by then a watcher has missed a deadline.

The lock, added as a safety mechanism, becomes a single point of total failure. Second time in this doc a safety mechanism has turned into the attack surface (see §18b, search and the spend ledger). Worth noticing as a pattern.

**Fix, three parts:**
1. **Lock has a TTL** longer than the maximum run wall clock, and it is heartbeated while the run is alive. A dead run's lock expires on its own.
2. **Timeouts at every level** (below).
3. **The stale-lock condition is logged and alarmed**, not silently recovered.

### 20a. Timeouts — none currently specified anywhere

Every one of these needs a number before Spec 2. A layer with no timeout is a layer that can hang forever.

| Level | Timeout | Notes |
| --- | --- | --- |
| Single HTTP fetch (city site) | OPEN | Connect and read timeouts set separately. |
| Single tool call | OPEN | |
| Model call | OPEN | |
| One agent invocation (wall clock) | OPEN | Backstop for the turn cap. Turn caps bound *steps*, not *time*. A single slow turn can outlast a whole run. |
| One document, end to end | OPEN | |
| Whole run | OPEN | Must be less than the lock TTL, which must be less than the schedule interval. |

**The ordering constraint is the important part: run timeout < lock TTL < schedule interval.** Violate it and runs either overlap or deadlock.

### 20b. Queue mechanics

The original handoff doc called for a queue with retry and a dead letter path. That never made it into this doc.

- **Delivery is at-least-once**, so consumers must be idempotent. They are, per §7 and §19a: content-hash ids and whole-document recovery mean a redelivered document overwrites rather than duplicates.
- **Visibility timeout** longer than the per-document timeout, or the same document gets handed to a second worker while the first is still on it.
- **Dead letter queue** for anything exceeding the attempt cap. DLQ contents are surfaced on the public reading log as parked documents with reasons, not hidden in the console.
- **DLQ is drained by a human decision**, never automatically. Automatic DLQ replay is how a poison document becomes a recurring bill.

### 20c. Concurrency

Currently unbounded, which is a cost spike and a politeness violation waiting to happen.

- **Max concurrent document extractions: OPEN, and low.** Every parallel extraction is a parallel model call. Unbounded fan-out on a day when the city posts twelve supplementals is exactly the scenario the spend ceiling would catch after the money is gone.
- **Max concurrent fetches against the city: 1.** This is a politeness obligation, not a tuning parameter. We are a guest on their server.
- **Watcher loop runs are serial per person**, and there is only one person's watchlist per invocation anyway (§3).

### 20d. Scheduler semantics

EventBridge fires the hourly trigger. Three behaviors need to be decided rather than discovered:

- **Missed fires: do not catch up.** If the system was down six hours, the next run does one run, not six. The work is defined by "what changed since the last successful read," not by a backlog of scheduled slots. Catch-up replay would multiply cost for zero additional information.
- **Double fires: harmless.** At-least-once delivery is expected, and the run lock absorbs it.
- **Last successful read time is the state that matters**, not the schedule. This is already how per-body timestamps work (§16b); stating it here makes the scheduler's role explicitly non-authoritative.

### 20e. Failure modes not yet classified

- **Crash-loop documents.** §16 classifies schema failures and timeouts. A document that hard-crashes the extractor every time is neither. **Rule: a crash counts toward the attempt cap and classifies as permanent on the second occurrence.** Otherwise a malformed PDF retries forever.
- **Model provider throttling.** Bedrock throttling exceptions are transient: backoff and retry next run. They are not a failure of the document.
- **Mid-run termination.** Serverless compute can be reclaimed. On SIGTERM, release the lock and record the run as interrupted. Interrupted is a real status, distinct from failed, and it appears in the reading log.
- **Deploy during a run.** Accepted risk, documented rather than engineered around. Solo build, hourly schedule, and the worst case is one interrupted run that re-does its documents next hour.
- **Backpressure.** If extraction lags ingestion the queue grows. At 21 bodies this is not a real risk, but the queue depth is logged so it would be visible rather than invisible if it ever were.

### 20f. No silent model fallback

A prior project used a second model provider as a fallback. **Not here.**

If the model provider is unavailable, the run fails closed and says so. A silent fallback to a different model would produce differently-worded rewrites, at different quality, with no signal to anyone that it happened. That is the civiq dense-floor defect wearing a different hat: a degradation that presents as a normal result.

Same posture for the embedding provider (§7). Failing loudly is the feature.

**Rewrite determinism:** temperature at or near zero for the rewrite call. It is a rewriting job, not a creative one, and reproducibility makes the golden set meaningful.

---

## Changelog (continued)

**Aug 16, 2026 (sixth pass — runtime and orchestration).** Added §20. The agents and the data were hardened; the layer that runs them was not.

- **FINDING: run-lock deadlock.** The lock required by §7 had no TTL and nothing in the build had a timeout. A single hung fetch would hold the lock forever and silently stop the watch, with no alarm that fires in useful time. Fixed with lock TTL plus heartbeat, timeouts at six levels, and an alarm on the stale-lock condition. Noted as the second instance of a safety mechanism becoming the failure surface (§18b was the first).
- **Timeout ordering constraint recorded:** run timeout < lock TTL < schedule interval. Six timeout values added as OPEN, all required before Spec 2.
- **Queue mechanics restored** from the original handoff doc: at-least-once delivery, visibility timeout longer than per-document timeout, DLQ surfaced publicly on the reading log, DLQ drained only by human decision.
- **Concurrency capped.** Document extraction concurrency OPEN and low; **fetches against the city capped at 1** as a politeness obligation, not a tuning knob.
- **Scheduler semantics decided:** missed fires do not catch up, double fires absorbed by the lock, and last-successful-read is the authoritative state rather than the schedule.
- **New failure classifications:** crash-loop documents (permanent on second crash), provider throttling (transient), mid-run termination (new "interrupted" status distinct from failed), deploy-during-run (accepted, documented).
- **§20f: no silent model fallback.** A second provider standing in silently would reproduce the civiq defect in a new form. Fail closed and say so. Rewrite temperature at or near zero so the golden set means something.

---

## 21. Prompt chaining — where it earns its place, and where it is banned

Taxonomy, so these do not get conflated: an **agent loop** is the model choosing its next action from an observation (three of these, §3). A **chain** is a fixed sequence of model calls, orchestrated by code, where each stage's output feeds the next. A loop is model-directed. A chain is code-directed.

Most of this build needs neither. Where a loop exists, chaining inside it is redundant. Two exceptions.

### 21a. The bilingual rewrite is a chain — CHAIN, and this resolves an ambiguity

§8 said Spanish is a first-class surface and never specified how it is produced. Three options existed and the choice matters:

1. One call producing both languages. Cheapest, and the worst: simplify-and-translate simultaneously is two jobs in one turn, and quality drops on both.
2. Two independent calls from the source. Parallel, not chained. Each is verifiable, but the two versions can diverge in emphasis and content, so a Spanish reader and an English reader get different products. Unacceptable for an access commitment.
3. **A chain: source → English plain-language rewrite → verify → translate the verified English → verify against source.** Chosen.

Why the chain wins: translating already-simplified text is a materially easier and more reliable task than simplifying and translating at once, and it **guarantees the two language surfaces say the same thing**, which is the whole point of calling Spanish first-class rather than an add-on.

The critical detail: **the Spanish output is still verified against the original source document, not against the English rewrite.** The chain is how it is produced. The source is what it is checked against. Otherwise an error in the English stage propagates into Spanish and both pass.

Cost note: this doubles rewrite calls. Rewrites are short outputs on already-narrowed page ranges, so the marginal cost is small against packet extraction, which is over 90% of spend.

### 21b. Rewrite → verify → retry is a chain, and it is already specified

§4. Worth naming as a chain so the shape is explicit: model call, deterministic check, conditional second model call with the failure reason attached. Code decides whether stage two runs. The model never does.

### 21c. BANNED: post-hoc explanation

The watcher must produce its match **and** its plain-language reason **in the same structured output**. Never a second call that explains a decision already made.

A model asked to explain a prior decision does not retrieve the reason. It manufactures a plausible one. That is confabulation with a receipt attached, which is worse than no receipt, because it looks like evidence. The explainability commitment in §3 is only meaningful if the reason is generated with the decision, not after it.

This is the same principle as §4's "the model does not grade its own output," pointed at a different failure.

### 21d. The governing rule

**No model call consumes another model call's output as if it were source.**

Every model call in this system anchors to the original document. The one deliberate exception is the translation stage in §21a, and even there the verification anchors back to the source. Chaining model outputs into each other is how a small error becomes a confident one, and it is invisible by the third hop.

Concretely, this bans: summarizing an item and then judging relevance against the summary (the watcher reads the item), extracting from a rewritten text rather than the packet, and drafting from a summary rather than from the extraction record.

---

## Changelog (continued)

**Aug 16, 2026 (seventh pass — chaining).** Added §21.

- **Resolved an ambiguity §8 left open:** how bilingual output is produced. Decided as a chain (source → English rewrite → verify → translate → verify against source) over one-call-both-languages or two independent calls. Rationale: translating simplified text is easier than simplify-plus-translate, and the chain guarantees both language surfaces say the same thing, which is what "first-class" has to mean. Verification anchors to the source in both stages, never English-to-Spanish.
- **Banned post-hoc explanation.** The watcher emits match and reason in one structured output. A second call asked to explain an existing decision confabulates a plausible reason rather than reporting the real one, which is worse than no reason because it looks like evidence.
- **Governing rule recorded: no model call consumes another model call's output as if it were source.** One deliberate exception (the translation stage), which still verifies against source.

---

## 22. Name and positioning

### 22a. The name is PORCH LIGHT

"Agenda Watch" is retired. It front-loaded a word the user does not use, carried a neighborhood-surveillance echo the whole product is designed against, and described the input rather than the promise.

**Aviso was proposed and killed on availability.** [Aviso AI](https://www.aviso.com/) owns aviso.com and is an established, funded AI revenue platform with PitchBook, G2, and Gartner Peer Insights presence. Same category. That also killed Aviso Previo and Plain Aviso, which share the head term.

**Porch Light** was chosen on four grounds:

1. **It threads the hardest constraint.** Somebody left the light on for you is hospitality, not surveillance. Every other candidate in the "watching" space fights the privacy stance in §6.
2. **It occupies genuine whitespace.** The civic tech naming landscape clusters into four crowded patterns: "Open" prefixes (Open311, OpenGov, Open States), imperative verb compounds (SeeClickFix, FixMyStreet, TheyWorkForYou), descriptive phrases (Public Input, Your Priorities), and classical references (Consul, Polis, Decidim). **Concrete everyday physical nouns are empty territory.**
3. **It survives naming research.** Lexicon Branding's rules favor names that create space rather than describe, carry attitude, and use emotional imagery. Measured against those, "Plain Notice" is a descriptive phrase in a category already saturated with descriptive phrases. Porch Light creates space and carries imagery.
4. **It holds up on the quiet week.** A porch light on an empty street is still doing its job. The product's most-seen screen and its name agree.

Availability: web search found no software conflict. The notable hit is a Philadelphia Mural Arts public art program, different category. **Not a trademark search.** Run USPTO before any brand investment.

Rejected and why: Plain Notice (safe, describes, forgettable), Early Word (low attitude), Fair Warning ("warning" fights the voice rules), Forum Clew and Civis Clew (portfolio consistency, but lands in the crowded classical cluster and reads inward to builders rather than outward to a tired volunteer), La Cuadra (opaque to the resident persona), Ojo (means "eye," wrong imagery for a privacy-first product).

**Note on bilingual:** the name does not need to be Spanish for the product to be genuinely bilingual. A warm English name with a first-class Spanish surface is honest. The Spanish requirement lives in §8, not in the wordmark.

### 22b. Competitive positioning — Curate

[Curate](https://www.curatesolutions.com/) is a direct competitor and finding it is good news.

**What they are:** an AI local legislative tracking platform scanning minutes, agendas, and planning documents from **more than 12,000 local government entities**, processing **over 400,000 minutes and agendas weekly**, with custom dashboards, daily email reports, and a database of 168,000+ local government contacts.

**Who they sell to:** businesses, trade associations, and local governments. Enterprise pricing, request-a-demo, sales-led, positioned around government relations and getting ahead of policy change.

**Three things this gives the submission:**

1. **It proves the problem is real and worth real money.** Someone built enterprise infrastructure around exactly this pain. Under the Potential Impact criterion, evidence beats assertion, and this is evidence.
2. **It proves the gap is precisely where we stand.** The monitoring a trade association can buy, a neighborhood volunteer cannot. No pricing page, no self-serve, no consumer product. The person doing this unpaid on a Friday night is not a customer segment to them.
3. **It sharpens the differentiation to one sentence.**

> Curate sells advocacy intelligence to organizations. Porch Light gives one person the same advance warning for free, in two languages, with a receipt on every claim and no ability to send anything on their behalf.

**Where this gets used, specifically:**

| Artifact | How |
| --- | --- |
| **Devpost description** | The differentiation sentence, close to verbatim, in the problem section. Name Curate. Naming a real competitor and stating the gap reads as market literacy, not weakness. |
| **README** | A short "Prior art and how this differs" section. Judges check whether a builder knows their space. |
| **Demo video** | One line, roughly ten seconds: this monitoring exists and it is sold to trade associations. The volunteer who needs it most cannot buy it. |
| **builder.aws.com post** | The framing for the whole piece: the gap between who can afford to watch and who needs to. |
| **§13 wind-down** | If this project is ever picked back up, Curate is the incumbent to re-check first. |

**What this does not license:** no claim to be better than Curate, no feature comparison table, no competitive teardown. They serve a different customer well. The honest claim is narrow and defensible: **that customer is not ours, and ours has nothing.**

Also worth stating plainly, since it is true and it is the kind of limitation this project names rather than hides: Curate covers 12,000 entities and we cover one city. Scale is not our claim. Reach is not our claim. The claim is that the person we serve currently has nothing at all.

---

## Changelog (continued)

**Aug 16, 2026 (eighth pass — name and positioning).** Added §22.

- **Name decided: PORCH LIGHT.** Agenda Watch retired. Aviso proposed and killed on a verified availability conflict with Aviso AI, an established AI software company. Porch Light chosen on surveillance-avoidance, category whitespace (concrete physical nouns are empty in a landscape full of "Open" prefixes, verb compounds, descriptive phrases, and classical references), naming-research fit, and coherence with the quiet-week state. Availability checked by web search only; USPTO check still required.
- **Recorded that the name need not be Spanish** for the product to be bilingual. That requirement lives in §8.
- **Competitive positioning added.** Curate identified as a direct competitor serving businesses, trade associations, and local governments at enterprise pricing. Used as evidence that the problem is real and that the gap is consumer-facing. Differentiation sentence written and assigned to five specific artifacts. Explicitly bounded: no superiority claim, no comparison table, and an honest statement that they cover 12,000 entities while we cover one city.

---

## 23. Copy decisions (running)

Small wording calls that are load-bearing. Anything here is binding on `voice.md` steering.

**The greeting: "Good afternoon, neighbor."** Lowercase. Varies morning / afternoon / evening by clock. Used once, at the top of the watcher surface, and nowhere else.

Rejected: a personal name ("Good afternoon, Maya"), which appeared in the first design pass. There are no accounts and we never learn a name, so a personal greeting implies knowledge the product deliberately does not have, sitting inches from "this list lives on your device, we never see it." Addressing the **relationship** rather than the person keeps the warmth and stays honest. It also reinforces the Good Neighbor Agents track without naming it.

**OPEN — the Spanish greeting is gendered.** *vecino* is masculine, *vecina* feminine. `vecino/a` is clunky in a warm greeting; `vecinx` and `vecine` are contested and read as a political statement to some readers; dropping the noun gives a clean *Buenas tardes* that loses the point. Placeholder is `Buenas tardes, vecindad` (neighborhood as a collective: natural, ungendered, keeps the relationship). **This is a question for the fluent reviewer in §8, not a call Claude or Shara should make unilaterally.** Good concrete first question for that reviewer.

Note the general pattern this surfaces: **an English surface can be gender-neutral by accident, and the Spanish equivalent cannot.** Every second-person or role-noun string in the product needs checking for this, not just the greeting. Add it to the bilingual review pass.

### Status colour semantics — binding

Discovered in the first design pass, where five amber warning triangles were used for "could not be read."

- **"Could not be read" is neutral information, not a warning.** Nobody did anything wrong. Neutral mark, muted colour, paired with a word.
- **Warm colours are reserved exclusively for an approaching comment deadline the user can still act on.** Nothing else in the product earns a warm colour, ever.
- Applying a warning colour to a public body not being reachable is a NEVER-list violation in visual form. The rule against saying "overdue" or "late" has a colour equivalent, and it is the same rule.

---

## Changelog (continued)

**Aug 16, 2026 (ninth pass — first design review).** Added §23.

- **Greeting decided: "Good afternoon, neighbor."** Replaces the personal-name greeting from the first design pass, which implied an account the product does not have.
- **Spanish greeting flagged OPEN** with a gendering problem and a placeholder, routed to the fluent reviewer. Generalised into a bilingual review requirement: English strings can be gender-neutral by accident where Spanish cannot.
- **Status colour semantics made binding** after the design pass used warning triangles for "could not be read." Warm colours are reserved for actionable deadlines only. A warning colour on an unreachable public body is the visual form of saying "overdue," and the same NEVER rule applies.
- Also caught in that pass and fixed in the build prompt: the design showed five consecutive identical failures for one body, which §16 layer 4 says should have quarantined it on day three. The quarantine state is now an explicit screen rather than an implied rule.

---

## 24. UI v1 accepted, and what remains before Spec 0

### 24a. Accepted

`claude/porch-light-ui-v1.html` is the reference UI for the quiet-week home screen. Dark warm palette, tokens exactly as specified in the UI direction doc, bilingual, WCAG 2.1 AA with computed ratios, quarantine state rendered, receipts present, no browser storage, no `innerHTML`, no `eval`.

Verified in review: focus ring on paper 6.01:1, quarantine border 3.53:1, reserved `--deadline` amber used nowhere, scroll regions keyboard focusable with `tabindex="0"` / `role="region"` / `aria-label`, `<time datetime>` present, Spanish complete including evidence strings, source document correctly left in English with a label.

**Polish backlog, non-blocking:** receipt font is 0.61rem and should be ~0.72rem (it is the core trust claim and currently the smallest text on the page); four identical "Open city page" link names need distinguishing accessible names; redundant `aria-label` alongside `aria-labelledby` on both side panels; disabled nav items need a visually-hidden reason; `overflow-x: hidden` on body masks rather than prevents; rotating mobile to desktop leaves the packet collapsed.

### 24b. Screens still to design

Only the quiet week exists. Ranked by value to the submission:

1. **Changed** — the active state. Item cards with the plain-language summary, the **why this matched** line, the full receipt, the deadline in city local time, and one action. **This matters more than the quiet week for the demo video**, because it is where the agent's value is visible.
2. **Draft scaffold** — structure and receipts filled, stance fields visibly and structurally blank (§4b).
3. **Search** — the resident's front door.
4. **Reading log, full page** — the public trust artifact. A fragment appears on the home screen already.
5. **Dormancy** — the honest end state (§13).

### 24c. Pre-build checklist

**Blocking Spec 0:**
- AWS Builder ID confirmed. Devpost registration confirmed. **Credits form submitted (deadline Sep 11, 12:00 PM PT).**
- Repo created, MIT or Apache license, civiq disclosure line in README, first commit dated after Aug 10.
- Kiro steering files written: `never.md`, `model-authority.md`, `security.md`, `style.md`, `voice.md`, `accessibility.md`.
- Agent Toolkit for AWS installed **with its rule file** (skills do not load without it).
- AgentCore CLI installed; legacy `bedrock-agentcore-starter-toolkit` uninstalled if present (same command name).
- **Spike A** (trivial Strands agent, two tools, local) and **Spike B** (same agent deployed to AgentCore). Spike B is the riskiest unknown in the project.
- Cost allocation tags activated and `run_id` propagation wired. Both are impossible retroactively.

**Blocking Spec 1:**
- Ventura's terms of use and robots.txt read.
- Real body list captured with real URLs (the mock uses "Riverdale" placeholders).
- Ingestion horizon window set.

**Blocking Spec 2:**
- All fourteen OPEN thresholds given values **and one-line rationales**: circuit-breaker failure percentage, quarantine consecutive-failure count, ingestion horizon, dormancy threshold, monthly spend ceiling, search rate limit, draft rate limit, extractor page-count cap, and the six timeout values (HTTP fetch, tool call, model call, agent invocation, per document, whole run). Constraint: **run timeout < lock TTL < schedule interval.**

**Blocking Spec 3:**
- Rewrite call path decided: Strands single call vs direct Converse.
- Strands SDK version pinned and recorded.
- Embedding provider chosen, with fail-closed behavior confirmed.
- **PII in logs: DECIDED — logs do not carry packet text.**

**Needed but not blocking:**
- LinkedIn URL and repo URL for the About footer (currently bracketed placeholders).
- Fluent Spanish reviewer identified. First concrete question: the gendered greeting (§23).
- Golden set: ~20 items hand-extracted from real Ventura packets and checked by eye. Real work, needs real packets.
- Demo video script. Draft it around Block 3, not Block 6 — if the demo cannot be narrated in five minutes, the build is too diffuse.

---

## Changelog (continued)

**Aug 16, 2026 (tenth pass — UI v1).** Added §24. UI v1 accepted after two correction rounds and saved as `claude/porch-light-ui-v1.html`. Six non-blocking polish items recorded. Five remaining screens ranked, with the Changed state flagged as more important than the quiet week for the demo video. Pre-build checklist assembled and grouped by which spec each item blocks. PII-in-logs decided: logs do not carry packet text.

---

## 25. The mock-to-real seam

Found Aug 22 while auditing whether mock-to-real wiring was actually accounted for. It was scheduled (Spec 6) but estimated as mechanical, and it is not.

### 25a. The finding

`porch-light-ui-v1.html` is internally inconsistent about data shape:

- **Check rows are data-shaped.** `{ datetime, body: {en, es}, evidence: {en, es} }`. This is close to a real view model.
- **Change cards are copy-key-shaped.** `{ statusKey: "hotStatus", headingKey: "hotHeading", receiptKey: "hotReceipt" }` — every field is a key into the COPY translation object, with the actual content living as static bilingual strings in COPY.

The second pattern is correct for UI chrome and **structurally incapable of carrying per-item database content**. The change cards are the most important screen in the product. Wiring them is not swapping an array; it is rebuilding how cards receive content.

### 25b. What the two-day Spec 6 estimate did not include

1. **No API/view contract is defined anywhere in this document.** The §data model is storage shape, not view shape.
2. **The i18n architecture has to split**: chrome strings stay in COPY; item content arrives from the database with both languages already generated and verified (§21a chain). One mechanism currently does both jobs.
3. **Degraded states are under-represented.** §16b names nine; the mock implements about three. Real data routinely yields unrewritten items (verifier failed twice → original staff text shown), unparsed documents, missing Spanish editions, null deadlines, and items with no clean page range.
4. **Riverdale → Ventura is not find-and-replace.** "Measure O Citizens Oversight Committee" is more than double "Planning Commission." Real item text runs longer than hand-tuned sample copy. This is the classic place mock layouts break.
5. **The packet panel's real-data content is undecided.** It is the hero visual of the product. Extracted text, PDF embed, and rendered page image look nothing alike and have different costs.
6. **Deadline rendering logic does not exist.** City local time, always labeled, relative phrasing computed against city time, DST test case (§2). In the mock these are static strings.

### 25c. Decision: contract-first fixtures

**At Spec 3**, when extraction first produces real items, define the **view contract** (the JSON the web layer consumes) and immediately convert the mock to read from `fixtures/sample.json` conforming to it. Chrome strings stay in COPY; everything item-specific moves to the fixture.

Ship a second fixture, **`fixtures/ugly.json`**, built from real Ventura strings and deliberately hostile: the longest real body name, an unrewritten item showing original staff language, a document that could not be read, a missing Spanish edition, a null deadline, an item with no clean page range, and an item summary at the 95th percentile of real length. **A layout that survives both fixtures is wired-ready.**

Then Spec 6 is swapping a fixture path for an endpoint, which genuinely fits two days.

Rationale: the standing principle is "mock data first, then wire APIs, never wire APIs to a broken layout." The unnamed step was always the **bridge** between them. The fixture *is* the bridge, and making it match the real contract early converts a risky integration into a path swap.

### 25d. Also moved earlier

- **Deadline rendering** (city local time, labeling, relative phrasing, DST) is built and tested at **Spec 3**, not Spec 6, because the fixture needs real timestamp values to render.
- **The packet panel decision** is made at **Spec 3** as well, since extraction determines what content is even available.

---

## Changelog (continued)

**Aug 22, 2026 (eleventh pass — mock-to-real seam).** Added §25 after auditing whether mock-to-real wiring was genuinely accounted for. It was scheduled but mis-estimated. Found that the mock's change cards are copy-key-shaped rather than data-shaped and cannot carry database content. Adopted contract-first fixtures: define the view contract at Spec 3 and convert the mock to read `fixtures/sample.json`, plus a hostile `fixtures/ugly.json` (longest real body name, unrewritten item, unreadable document, missing Spanish edition, null deadline, no clean page range, 95th-percentile summary length). Moved deadline rendering logic and the packet-panel content decision from Spec 6 to Spec 3.

---

## 26. Deployment topology, and the watcher/watchlist contradiction

Surfaced Aug 22 while deciding whether the web layer could live on Vercel. The deployment question was easy; checking it exposed a real contradiction between §3 and §6.

### 26a. Docker is not required — verified

Confirmed against AWS docs, Aug 22 2026:

- **`agentcore deploy` builds remotely.** Verbatim from the AgentCore CLI docs: *"A local runtime is not required for `agentcore deploy` — AWS CodeBuild builds the image remotely."* Docker/Podman/Finch are used only by `agentcore dev` and `agentcore package`.
- **Direct code deployment avoids containers entirely.** A .zip of code plus dependencies. Max 250MB (we are far below), faster updates, explicitly recommended for rapid iteration. Container deploy only wins above 250MB or with specialized dependencies.

**Decision: direct code deployment. No Docker in the deploy path.**

**Docker is still MUST for one job:** `docker-compose.yml` providing local Postgres + pgvector. This exists for the Spec 7 gate ("a stranger can clone and run it"), not for deployment. A judge with Docker gets a working database in one command.

### 26b. Deployment topology

| Layer | Host | Rationale |
| --- | --- | --- |
| Frontend + read-only search API | **Vercel** | Ideal fit; provides the live demo link the rules say strengthens Technical Implementation. |
| Hunter, extractor, watcher agents | **AgentCore** (direct code deploy) | Explicitly rewarded by the rules. Also long-running beyond serverless comfort. |
| Scheduler | **EventBridge**, not Vercel Cron | Vercel Hobby throttles cron frequency; hourly would fight it. EventBridge was already the plan (§20d). |
| Postgres + pgvector | **Neon** | Reachable from both. Proven at this scale in civiq. |

Verified Vercel limits (Aug 2026): function max duration 300s Hobby / 800s Pro, request+response payload 4.5MB, memory 2GB Hobby. All comfortable for a read-only API.

**This split is not a compromise — it is the architecture we already had.** The original handoff doc specified a background pipeline and a read-only site that never talk to each other, joined only by the database, so a broken pipeline still leaves the site serving with an honest last-read timestamp. That is exactly the Vercel/AgentCore boundary.

### 26c. FINDING: §3 and §6 contradicted each other

**§3** described the watcher loop as running "per person, per run" on a schedule. **§6** established that the watchlist never leaves the browser.

Both cannot be true. A scheduled server-side watcher has no watchlist to run against, because we deliberately never stored one.

**Resolution: the reading is scheduled, the matching is live.**

- Hunter and extractor run hourly in AgentCore, storing items with verified bilingual summaries. This is the pipeline the heartbeat describes.
- **The watcher runs on demand**, when a person opens the page. The browser sends the watchlist, the agent reasons over what is new since that person's last-seen marker, returns matches with reasons, and **stores nothing**.
- Therefore the Vercel layer **does** invoke AgentCore at request time. AWS credentials live in Vercel environment variables, server-side only.

**Consequence 1 — a verbatim string becomes untrue and must change.** "This list lives on your device. We never see it" is false once we transmit it for matching. Replace with:

> **"Your list stays on your device. We use it to answer, and never store it."**
> ES: **"Su lista permanece en su dispositivo. La usamos para responderle y nunca la guardamos."**

Weaker sounding, actually true. This is the honest-over-optimistic rule applied to our own marketing. Update `voice.md`, the mock, and the About footer's "It never stores your watch list" line (which remains accurate as written).

**Consequence 2 — every page open costs a model call.** Same cost-drain and availability vector as §18b. Mitigations, all required: rate limit watcher invocations per IP, cache matches client-side keyed on (watchlist hash + last-seen item id) so reopening does not re-run the agent, and give the watcher its own spend sub-budget separate from ingestion and search.

**Consequence 3 — the cold-start rule (§3) still applies**, now framed as first-open rather than first-run: the first time a watchlist is seen, establish a baseline quietly rather than returning every historical match.

**Unaffected:** the mock's design is correct as-is. The heartbeat describes the pipeline; matches are computed when you look.

### 26d. Secrets across two clouds

- Vercel env vars hold: Neon connection string, AWS credentials scoped to invoking **only** the watcher agent (not the hunter or extractor roles), and nothing else.
- The watcher's invocation role is a fourth, narrower identity than the three execution roles in §19c. It can invoke; it cannot deploy, read logs, or touch other agents.
- No AWS credentials ever reach the browser.

---

## Changelog (continued)

**Aug 22, 2026 (twelfth pass — deployment).** Added §26.

- **Docker verified unnecessary for deploy** (CodeBuild remote build; direct code deployment via .zip). Kept as MUST for local dev only via docker-compose with Postgres+pgvector, serving the Spec 7 "stranger can clone and run it" gate.
- **Deployment topology decided:** Vercel (frontend + read-only API), AgentCore (three agents, direct code deploy), EventBridge (schedule, avoiding Vercel Hobby cron throttling), Neon (Postgres+pgvector). Noted that this split is the pipeline/site seam the architecture already specified.
- **FINDING: §3 and §6 contradicted each other.** A scheduled per-person watcher is impossible when the watchlist is never stored. Resolved as: reading is scheduled, matching is live on page open, watchlist transmitted but never stored. Vercel therefore invokes AgentCore at request time.
- **A verbatim load-bearing string changed** because it became untrue: "This list lives on your device. We never see it" → "Your list stays on your device. We use it to answer, and never store it." Honest over optimistic, applied to our own copy.
- Watcher invocations added to the rate-limit and spend-sub-budget regime; client-side match caching required; cold start reframed as first-open.
- Fourth narrow IAM identity added for Vercel-to-watcher invocation, distinct from the three execution roles.

---

## 27. Model selection

Decided Aug 22 after checking Bedrock pricing. Previously §tech said only "Models: Bedrock," which was an unmade decision wearing a decision's clothes.

### 27a. Decision

**Spec 0 proves invocation on Amazon Nova Lite (`amazon.nova-lite-v1:0`). The production model is chosen at Spec 3 on measured evidence.**

Spec 0's job is proving the pipe works. Nova has no AWS Marketplace subscription gate (Anthropic models require a one-time First Time Use form per account, which can involve org approval and is outside our control), so it is the fastest path to a proven invocation and commits nothing.

**The model id is read from configuration, never hardcoded**, so the Spec 3 decision requires no code change. The model id appears in every structured log event so any measurement run is attributable.

### 27b. Pricing, verified Aug 22 2026 (input tokens per million)

| Model | Input | Notes |
| --- | --- | --- |
| Nova Micro | $0.035 | 128K context |
| **Nova Lite** | **$0.060** | 300K context; cached input $0.015 |
| Nova Pro | $0.80 | |
| Claude Sonnet | ~$6.00 | As rendered on the Bedrock pricing page; confirm for the specific model before relying on it. |

Roughly **100x on input** between Nova Lite and Claude Sonnet.

**At our scale that difference is smaller than it sounds.** Estimating from civiq's real corpus, two-pass extraction plus bilingual rewrites lands around 2–3M input tokens/month: about **$0.18/month on Nova Lite versus about $18 on Claude Sonnet.** Both fit inside $50 of credits.

**Where cost actually bites is development, not production.** Extraction gets re-run dozens of times while debugging Spec 3, tuning the verifier, and building the golden set. That iteration spend is what surprises people, and 100x headroom is worth real money against a small fixed budget.

### 27c. The honest scoring note

**"AWS hackathon, therefore Nova" is not a scoring argument.** Technical Implementation is judged on "how thoroughly and skillfully does the project use Strands Agents." Model choice is not a criterion anywhere in the rules. Choosing Nova to please AWS judges would be vibes, not points.

**What is worth points is the measurement.** The six-check verifier (§4) plus the golden set (§11) turn model choice from an opinion into a number: **verifier rejection rate per model on the same real packets.** Publishing that comparison is more interesting to an AWS Developer Advocate than either choice by itself.

Worth naming for the writeup: **the verifier is what makes trying the cheap model safe.** A weaker model's fabrications get caught rather than shipped. The rigor bought the optionality.

### 27d. What gets decided at Spec 3

Two numbers, same real packets, both models:
1. **Verifier rejection rate** (how often output fails the six checks, in both languages).
2. **Measured cost per packet**, extrapolated to a month.

Pick the cheapest model that clears the quality bar. Record the comparison. This becomes a builder.aws.com post (§11 — posts are worth 0.2 each, up to 0.6 for three).

**Per-job model splitting is a STUB, not a plan.** Cheap model for high-volume extraction, stronger model for nuanced relevance judgment, is defensible and probably optimal. It also doubles the integration surface in a 23-day build. Note it; build it only if the Spec 3 numbers make the case obvious.

### 27e. This does not conflict with the no-silent-fallback rule

§20f and `never.md` forbid **silent model fallback**: a degraded run quietly switching providers mid-flight and presenting the result as normal. That ban stands unchanged.

A deliberate, documented, configuration-level model choice made on measured evidence is the opposite. **The test, if the two ever look like they collide in code: did a human choose it and write down why, or did the system substitute on its own during a run.**

---

## Changelog (continued)

**Aug 22, 2026 (thirteenth pass — model selection).** Added §27, closing an unmade decision that §tech had been carrying as "Models: Bedrock."

- **Spec 0 uses Nova Lite**, chosen because it has no Marketplace subscription gate and therefore proves invocation fastest. Commits nothing about production.
- **Model id read from configuration, never hardcoded**, and included in every structured log event so measurement runs are attributable.
- **Production model deferred to Spec 3**, decided on two measured numbers: verifier rejection rate on identical real packets, and cost per packet. Bedrock pricing verified: Nova Lite $0.060/M input vs Claude Sonnet ~$6.00/M, roughly 100x, though at our scale that is ~$0.18/month vs ~$18/month. **The real cost exposure is development iteration, not steady state.**
- **Recorded that "AWS hackathon therefore Nova" is not a scoring argument** — model choice appears in no judging criterion. The measurement is what scores, and it becomes a builder.aws.com post.
- **Noted that the verifier is what makes trying a cheap model safe**, which is the rigor buying optionality.
- Per-job model splitting recorded as STUB, not plan.
- Clarified that a documented configuration-level choice does not conflict with the §20f silent-fallback ban; the test is whether a human chose it and wrote down why.


---

## 31. Spike B result and repo hygiene for a public repo

Spike B passed (structlog proven in the AgentCore runtime, redaction and truncation firing in CloudWatch, third-party logs inheriting bound context). The details live in the Spec 0 tasks.md RESULT lines. This section records only the decision that came out of hardening the repo for public judging.

### 31c. Account-specific AgentCore files: a three-way split

The repo becomes public for hackathon judging. Three tracked files carried our 12-digit AWS account ID (elided here as `831…571`, deliberately not written in full anywhere in the repo), embedded in resource ARNs and an IAM role ARN. An account ID is not a credential, but it is a low-severity disclosure that narrows an attacker's surface (role-assumption guessing, targeted phishing) and is hard to rotate. It does not belong in a public repo.

Three files, three different correct treatments, because they are three different kinds of thing:

1. **`agentcore/.cli/deployed-state.json` — vendor output, regenerable.** The AgentCore CLI writes it as an output of `agentcore deploy`. A fresh clone regenerates it on first deploy. **Decision: gitignore it.** This **overrides the vendor's own `.gitignore`**, which explicitly un-ignores this file (`!.cli/deployed-state.json`) on the assumption of a private repo. That assumption does not hold for us. The override is placed in the ROOT `.gitignore` so the nested vendor file cannot re-un-ignore it.

2. **`agentcore/aws-targets.json` — required input config, not regenerable.** The CLI reads it to know which account and region to deploy into. A fresh deploy needs it before it can run, and the CLI does not reconstruct it from AWS. **Decision: treat it exactly like `.env`** — gitignore the real file (keeps the real account ID on disk so deploys keep working) and commit `aws-targets.json.example` with `"account": "<AWS_ACCOUNT_ID>"` and the real region. A judge copies the example and fills in their own 12-digit account ID. Placeholdering a *tracked* copy was rejected: the real ID would have to go back in to deploy, git would then show it modified, and the only thing keeping it out of the next commit would be a human remembering — the §32c "guarantee that depends on remembering" pattern.

3. **`tasks.md` — our spec document, belongs in the repo.** Cannot be gitignored; it is the record. **Decision: replace the account ID and role ARN in the text with `<AWS_ACCOUNT_ID>` and a placeholder role name, keeping the RESULT lines intact** (they are the record; only the identifiers come out).

### 31d. History rewrite

`git rm --cached` and redaction only stop the leak going forward. The account ID stayed readable in commits via `git log -p`. With no remote configured and only a handful of commits, this was the cheapest it would ever be to fix; after a push it means force-pushing over published history.

`git-filter-repo` (2.47.0, installed via `uv tool install`) was run over the full history: `--replace-text` mapping the literal account ID to `<AWS_ACCOUNT_ID>`, plus `--invert-paths` removing both vendor file paths from every commit. The commit narrative survived (same messages, same order; hashes changed as any rewrite requires). Verified zero results from `git grep` and `git log -S` for the literal account ID (the digits are passed on the command line only, never written into a tracked file, or the check would match its own documentation), and re-verified a deploy still works afterward. These two checks are now part of the Spec 0 close checkpoint (task 19), so the absence is verified rather than assumed.

### 31e. FINDING: the CloudWatch log group is untagged

Task 13.1 (cost tag verification) found that all four cost tags are present on the AgentCore runtime, its runtime endpoint, the workload identity, and the IAM execution role. The **CloudWatch log group is the exception: it carries no tags at all.**

This is not the "resource type does not support tagging" case that Requirement 7.3 anticipates. CloudWatch log groups support tags. The cause is that AgentCore creates the log group implicitly at first runtime execution, outside the CloudFormation resource set that the CDK tags. So the tagging path that covers every declared resource never touches it.

Recorded as a genuine gap against Requirement 7.1, not waved off. It is not hand-patched at Spec 0: manually tagging a resource the vendor recreates would be state living outside the repo with nothing keeping it in sync, which is the pattern this project keeps refusing. Per the 7.3 note, automated tag enforcement lands in a later spec once infrastructure-as-code owns the log group. Until then the gap is documented and visible rather than silently assumed closed.

---

## Changelog (continued)

**Aug 26-27, 2026 (Spike B close — repo hygiene).** Added §31.

- **Spike B passed** with the strong version of the proof: our structlog schema in CloudWatch, redaction and truncation markers firing in the deployed runtime, third-party logs inheriting bound context.
- **§31c: account-specific AgentCore files split three ways** for a public repo. `deployed-state.json` gitignored (regenerable vendor output), overriding the vendor's own un-ignore default on the ROOT gitignore. `aws-targets.json` treated like `.env` with a committed `.example` (required input config, not regenerable). `tasks.md` redacted in place with placeholders, RESULT lines kept.
- **§31d: full git history rewritten with git-filter-repo** to remove the account ID and the two vendor file paths from all commits. Verified zero via `git grep` and `git log -S`, deploy re-verified, and both checks added to the task 19 close checkpoint.
- **§31e: CloudWatch log group found untagged** during task 13.1. All four cost tags present on the runtime, endpoint, workload identity, and IAM role; the log group carries none because AgentCore creates it implicitly at runtime, outside the tagged CloudFormation set. Documented as a real Requirement 7.1 gap, deferred to IaC-owned enforcement rather than hand-patched.


---

## 33. Database: Aurora Serverless v2, not Neon

Neon (§tech, §26b) is retired as the production database. **Amazon Aurora Serverless v2 PostgreSQL replaces it.**

### 33a. Why the change

- **The $10k in AWS credits removes Neon's rationale.** Neon was chosen partly for its free tier. With credits, staying inside AWS costs effectively nothing at this scale and removes a non-AWS box from an otherwise all-AWS architecture diagram, in an AWS agent hackathon where that box is an avoidable dent.
- **DynamoDB was considered and rejected.** The data and queries are relational: joins across meetings, items, and documents, plus lexical search, vector search, and rank fusion. DynamoDB has neither joins nor vector search. Forcing this data into a key-value store would be fighting the tool.
- **Aurora keeps pgvector.** Same Postgres + pgvector code path already proven locally (§5, §7), so the search design does not change.

### 33b. Two configuration constraints

1. **Minimum capacity 0.5 ACU, not 0.** §26c invokes the watcher live from the web layer when a person opens the page. Aurora resuming from zero capacity takes roughly fifteen seconds, which is a blank screen while someone waits. Credits absorb the cost of staying warm; a cold-start delay in front of a waiting human is not acceptable when the money reason for allowing it has been removed.
2. **Access via the RDS Data API (HTTPS + IAM), not a VPC connection.** This keeps the web layer out of a VPC and avoids a NAT gateway entirely. The site talks to Aurora over signed HTTPS, consistent with the rest of the deployment posture.

### 33c. When

**Aurora setup is a Spec 2 task, not Spec 0.** No database is touched before Spec 2. Local docker-compose Postgres + pgvector covers Specs 1 and 2 completely. The Spec 0 task that would have created Neon (task 15.1) is cancelled, not deferred. `.env.example` carries a credential-free Aurora RDS Data API placeholder (cluster ARN, secret ARN, database name) in place of the old Neon connection string.

---

## Changelog (continued)

**Aug 27, 2026 (Spec 0 close — database change).** Added §33.

- **Database changed from Neon to Amazon Aurora Serverless v2 PostgreSQL.** $10k credits remove Neon's free-tier rationale and an all-AWS diagram avoids a non-AWS dependency. DynamoDB rejected because the data and queries are relational (joins, lexical + vector + rank fusion), which it does not support. pgvector retained, so the search code path is unchanged.
- **Two constraints recorded:** minimum 0.5 ACU (not 0, because the live watcher invocation cannot sit behind a ~15s cold resume), and RDS Data API access (HTTPS + IAM, no VPC, no NAT gateway).
- **Spec 0 task 15.1 (Neon) cancelled**, Aurora setup moved to the Spec 2 backlog. No database touched before Spec 2; local docker-compose Postgres covers Specs 1 and 2. `.env.example` updated with a credential-free Aurora Data API placeholder.


---

## 41. Never verify by inference what the record already states

A general principle, surfaced Aug 31 while fixing the W6 body-name hole (a rewrite
naming "City Council" on a Planning Commission agenda passed the entity checks
because §decision-1 had removed body names from raw-compare, and reading level
caught it only by luck).

**The principle: a deterministic field on the record is checked for CONTRADICTION,
not matched as an entity learned from the document.**

Entity matching (verifier checks 2, 3, 6) is for facts we LEARN from the document
text — numbers, dates, amounts, street names, identifiers. Those must trace back
to the source page range, so they are extracted and compared. The BODY is not one
of those. It comes off the extraction record deterministically (never.md #1: body
is copied, never model-generated). Asking the verifier to re-match the body as a
free-text entity made it re-derive a fact it already held with certainty, and that
re-derivation is what was brittle: the proper-noun extractor captures greedy spans
("City Council Minutes"), so "City Council" could not match, and the drop list that
hid this then made a substituted body name invisible.

**The fix that generalizes:** for a deterministic record field, add a
CONTAINMENT-style check (check 4) that rejects a rewrite CONTRADICTING the field,
using a small closed registry of accepted renderings (EN + accepted ES), not a
free-text entity match. Language-independent: a Spanish rendering of the wrong body
fails exactly like the English name. Absence of the field in the rewrite is
reported (a count), not rejected in v1.

**Where else this applies:** any field the record holds deterministically and the
rewrite might restate — the body (built, §check-4 body-consistency), and
potentially the meeting date or item number if a future rewrite surface restates
them in prose. The item number, page range, and deadline are already
containment-checked (check 4), consistent with this principle; the body-consistency
rule extends the same idea to the body, with a bilingual registry because the body
name legitimately translates while an item number does not.

Corollary recorded for the write-up: entity matching is for what we LEARN; the
record is for what we KNOW. Do not check the second with the machinery of the first.


---

## 42. Two containment findings from the live extractor deploy (R5)

Both surfaced deploying the extractor to AgentCore Runtime and proving the
tool-allowlist hook live (Spec 3 R5, 2026-08-31). They are recorded because they
are the strongest security-story material in the build: guarantees proven by a real
failure and a real block, not asserted.

### 42a. never.md #7 (fail closed) proven live by a real SDK break

The first deploy of the extractor **refused to run**. The allowlist hook imports a
Strands hook event, and the symbol name was wrong for the deployed SDK version:

- **Wrong (my code):** `from strands.hooks import BeforeToolInvocationEvent`
- **Right (strands-agents 1.53.0):** `from strands.hooks import BeforeToolCallEvent`
  (and `event.tool_use` is a mapping — read `["name"]`, not an attribute).

Because `_register_allowlist_hook` is written to raise rather than run an unguarded
agent, the runtime failed CLOSED: CloudWatch showed
`RuntimeError: extractor tool-allowlist hook unavailable; refusing to run unguarded`
and the invocation produced no extraction. This is never.md #7 (never fail open)
proven against the deployed runtime rather than asserted in a comment — a broken
guard stopped the agent instead of silently letting it run without the guard. Fixed
the symbol, redeployed, and the hook then blocked as designed.

### 42b. Test the control, not the thing the control sits behind

The first containment probe planted a tool named `fetch_url` and prompted the model
to call `http://attacker.example/exfil`. **Nova Lite refused it on its own safety**
("I can't help with a request to an external URL that may compromise security"), so
the model never attempted the tool and **our hook never fired**. A green result
there would have measured the MODEL'S ALIGNMENT, not our allowlist — a false proof.

The valid test plants a **benign, plainly-safe tool that simply is not on the
allowlist** (`count_words`) and asks the model to use it normally. The model calls
it, and the hook blocks it by NAME:
`{"event":"never_trip_tool_blocked","tool_name":"count_words","boundary":"tool_allowlist","level":"warning"}`,
then a `PermissionError` terminates the run before the tool executes.

**Principle, recorded:** TEST THE CONTROL, NOT THE THING THE CONTROL SITS BEHIND.
Our allowlist blocks by tool NAME, independent of intent, so the test must exercise
the name check — which a benign non-allowlisted tool does and a malicious one does
not (it gets refused upstream by the model). This is the same class as §28 (green
tests over broken reality): a test that passes for the wrong reason is worse than no
test. Promoted to a live smoke test (`tests/live/test_smoke_extractor_containment.py`,
`make smoke`) so the allowlist firing is re-checked on demand, per testing.md
obligation 1.

---

## Changelog (continued)

**Aug 31, 2026 (R5 — extractor deployed to AgentCore).** Added §41 (never verify by
inference what the record already states — the body-consistency check) and §42 (two
live-deploy containment findings). The extractor now runs on Bedrock AgentCore
Runtime (PUBLIC networkMode; VPC no-egress designed, committed, deferred
post-submission — see KNOWN-LIMITATIONS three-layer entry). Tool-allowlist hook
proven live (NEVER-trip + fail-closed). Migrations 002/003/004 applied to Aurora.
IAM invoke on the extractor runtime scoped to `porchlight-dev-hunter-role`, that ARN
only. Containment promoted to a `make smoke` live test.


---

## 43. Green-and-broken finding #6: the extractor agent had no tools (an absence, not a defect)

Found while mapping the condition-5 join (2026-08-31), before writing any code.
This is the sixth green-and-broken finding of the build and the **first that is an
absence rather than a defect** — nothing was wrong in what existed; the failure was
in what was never there, and no test could go red because no test asserted the thing.

**What we found.** The extractor's tool allowlist names four tools —
`find_listing_pages`, `get_document_pages`, `extract_items`, `record_items`
(`agents/extractor/tools.py`). **None of the four has a body.** `tools.py` contains
only `is_tool_allowed`, the `ExtractedItem` dataclass, and `validate_items`. The
deployed entrypoint calls `build_agent(MODEL_ID, tools)` with `tools = list(payload
.get("_tools", []) or [])` — i.e. an **empty list** in normal operation (only the
containment probe ever adds a tool). `build_agent` hands that empty list to the
Strands `Agent` alongside a system prompt that instructs the model to "use only your
provided tools." So the deployed extractor is an agent **with no tools, told to use
its tools**, streaming events and returning no structured items across the invoke
boundary.

**Why every test stayed green.** The tests covered the allowlist (`is_tool_allowed`
by name), `validate_items` (the source-fidelity guard), and — live — the containment
hook (a probe tool the model calls and the hook blocks). All real, all passing. But
**nothing asserted the agent actually had tools**, and nothing ran an extraction end
to end through the model. W6 (`tests/golden/w6_live_run.py`) proved the rewrite→
verify→persist half live, with the extracted `ITEMS` **hand-copied from the PDF** —
the extraction step was literal data, never a model run. So "the extractor works"
was true of every piece we tested and false of the whole, because the whole was
never assembled or exercised.

**The class of failure.** The five prior green-and-broken findings were defects: a
check too strict, a glyph map too narrow, a hardcoded string missing diacritics.
This one is an **absence** — the tools were named in an allowlist and referenced in a
prompt, which reads as intent to a human skimming the file, but the implementation
was simply not there, and the test suite mirrored the same gap (it tested the
guardrails around the tools, never the tools). The lesson for testing.md: an
allowlist entry and a prompt sentence are not evidence a capability exists; a test
must exercise the capability itself. A named-but-absent thing is invisible to tests
that only check the naming.

**What we are doing about it.** Building the four tool bodies (Option A) so the
extractor is a genuine tool-using agent — gated by a spike first (§working-style:
spike before building; 15-minute Nova-Lite tool-use reality check, 3/3 pass/fail, no
prompt iteration to rescue a FAIL). If the spike fails, we fall back to a
structured-output extraction call (Option B) and say so plainly, not dressed as A.
If both fail, the floor is deterministic extraction for these known meetings (Option
C) with the model-driven extractor deployed and its containment proven but item
selection not model-driven — written into KNOWN-LIMITATIONS now, before the spike,
the same way the network-egress layer was written honestly before it was resolved.
