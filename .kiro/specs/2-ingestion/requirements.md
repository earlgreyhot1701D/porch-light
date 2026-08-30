# Requirements Document — Spec 2: Ingestion

## Introduction

Spec 2 builds the layer that RUNS the Spec 1 adapter on a schedule, safely and
within budget: the EventBridge schedule, the run lock with TTL and heartbeat, the
work queue, change detection via content hash, the five-layer retry budget, the
application-level spend ledger, the run log, and the observability wiring. It also
provisions the production database — Amazon Aurora Serverless v2 PostgreSQL — and
lands the schema the adapter's records are written to.

Spec 2 does not extract item text or call a model (Spec 3), and does not build the
public site (Spec 6). It turns "the adapter can parse Ventura once" into "the
adapter runs every hour, writes nothing twice, spends nothing it should not, and
says honestly what it did."

References decisions §7 (change detection, idempotency, good-citizen posture),
§16a (five retry layers), §17 (run log, observability, identifiers), §18/§18b
(13-layer reality, spend ledger, security sweep), §20 (run-lock deadlock finding,
timeout ordering, concurrency, no silent model fallback), §33 (Aurora setup). The
fourteen thresholds are named in Spec 1 R8; Spec 2 is where the OPEN ones get
finalized.

## Rigor budget (style.md)

Feature code, **working rigor**: it must do the right thing on real runs against
real data. **Property tests only where a wrong answer is invisible** — here that
is idempotency (a re-run must write nothing new) and the retry-classification
logic (transient vs permanent). Not on the schema DDL, config, or status strings,
which are verifiable by reading. The pass gate is behavioral: a second run on
unchanged data does nothing and says so; a crashed-and-restarted run double-writes
nothing.

## Glossary

- **Run**: one scheduled pass of the pipeline, identified by a `run_id` (§17a).
- **Run lock**: the mutex that prevents overlapping runs, with a TTL and heartbeat (§20).
- **Change detection**: deciding a document is new/changed by content hash (§7).
- **Spend ledger**: the application-level record of spend, checked before a run starts (§16a layer 5, §18b).
- **Quarantine**: a body stopped after N consecutive failed runs (§16a layer 4).
- **Circuit breaker**: stopping a single run when too many documents in it fail (§16a layer 3).
- **Aurora**: Amazon Aurora Serverless v2 PostgreSQL, reached via the RDS Data API (§33).

## Requirements

### Requirement 1: Schedule (EventBridge, not Vercel Cron)

**User Story:** As the operator, I want the pipeline to run hourly on a reliable
schedule, so that new agendas are found without me watching.

#### Acceptance Criteria

1. THE Pipeline SHALL be triggered by an EventBridge schedule, never Vercel Cron (§26 topology).
2. THE schedule interval SHALL be hourly (T14 = 60 min), honoring the good-citizen
   "hourly, not continuous" posture (§7).
3. WHEN a scheduled trigger fires while a run is already in progress, THE Pipeline
   SHALL NOT start a second overlapping run (see Requirement 2).
4. WHEN scheduled triggers were missed (the system was down), THE Pipeline SHALL
   perform ONE run on the next trigger, not a backlog catch-up of missed slots
   (§20d — work is defined by "what changed since last successful read").

### Requirement 2: Run lock with TTL and heartbeat (the §20 deadlock finding)

**User Story:** As the operator, I want a hung run to release its lock
automatically, so that one stuck fetch never silently stops the watch forever.

#### Acceptance Criteria

1. THE Pipeline SHALL acquire a run lock before doing work and SHALL NOT start if
   the lock is held by a live run.
2. THE run lock SHALL have a TTL (T12 = 15 min) so a dead run's lock expires and
   the schedule recovers without human intervention (§20 — the deadlock finding).
3. A live run SHALL heartbeat the lock so a long-but-healthy run does not lose its
   own lock before finishing.
4. THE timeout ordering SHALL hold: **run timeout (T11=10m) < lock TTL (T12=15m) <
   schedule interval (T14=60m)** (§20, §7). A test SHALL assert this ordering.
5. WHEN a run is reclaimed mid-flight (SIGTERM / serverless reclaim), THE Pipeline
   SHALL release the lock and record the run as `interrupted` — a real status
   distinct from `failed` (§20e) — surfaced in the run log.
6. A stale-lock condition SHALL raise an alarm (§17, §18b alarm 9-class).

### Requirement 3: Change detection and idempotency (§7)

**User Story:** As the operator, I want a second run on unchanged data to write
nothing new, so that re-runs and restarts are safe and cheap.

#### Acceptance Criteria

1. THE Pipeline SHALL detect a new or changed document by **content hash**
   (`document_id`, Spec 1 R3.7) — this is the CORRECTNESS mechanism. Conditional
   GET (`Last-Modified`/`ETag`) is an OPTIMIZATION to skip re-downloading unchanged
   documents when the server's headers are trustworthy; **its savings are not
   guaranteed** (§39: the city batch-touched all 152 files to one `Last-Modified`,
   making every document look changed). When conditional GET does not help, the
   content hash still yields the right answer: re-downloaded-but-identical bytes
   hash to the existing id and write nothing. Correctness never depends on the
   header (§7, amends Spec 1 R7.3).
2. WHEN a run processes a document whose content hash already exists in storage,
   THE Pipeline SHALL NOT create a duplicate record and SHALL NOT re-do downstream
   work for it (idempotency, §7).
3. WHEN a run crashes partway and restarts, THE Pipeline SHALL NOT double-write any
   record it had already written (idempotency guarantee with a test, §7). This is
   half the pass gate.
4. Idempotency SHALL be verified by a property/behavioral test: running twice over
   the same fixed input yields the same stored state as running once.

### Requirement 4: In-process work list and per-document status [queue is STUB]

**User Story:** As the city's server, I want this reader to fetch politely and one
at a time; and as the operator, I want a restart to resume rather than repeat,
without distributed-systems machinery a serial ~90-second run does not need.

Rationale (rigor budget applied to infrastructure, §32c): the workload is ~15
in-horizon meetings, ~35 fetches, max 1 concurrent, one process, finishing in
about 90 seconds. A message queue with at-least-once delivery, visibility
timeouts, and a DLQ would add failure modes that do not otherwise exist. The pass
gate ("a crashed-and-restarted run double-writes nothing") is met by content-hash
idempotency (R3) plus a per-document status column, not by a queue.

#### Acceptance Criteria

1. THE Pipeline SHALL process changed documents from an **in-process work list**
   over the in-horizon documents, ordered deterministically (so a re-run visits
   them in the same order).
2. THE Pipeline SHALL track **per-document status in the database**: one of
   `pending`, `in_flight`, `done`, `parked` (transient, auto-retry next run), or
   `permanent_fail` (never auto-retried). A restart resumes from status rather than
   repeating completed work (this, with R3 idempotency, meets the crash-restart
   pass gate).
3. Fetch concurrency against the city SHALL be at most 1 (§7 politeness), inherited
   from the Spec 1 fetch layer.
4. A document that fails permanently after its retry budget (R5) SHALL be marked
   `permanent_fail` and surfaced in the run log, cleared only by a human decision.
5. **STUB (v2, not built):** an SQS work queue with visibility timeout and a DLQ.
   The condition that would justify building it: more than one city, or a run that
   no longer fits in one process within T11. A comment stub in the pipeline names
   this path and this condition; no queue infrastructure is provisioned in Spec 2.

### Requirement 5: The five-layer retry budget (§16a)

**User Story:** As the operator, I want retries bounded and classified, so that an
hourly loop never grinds against a broken document for a month or spends money to
fail identically.

#### Acceptance Criteria

1. **Layer 1 — attempts per document per stage: exactly 2** (first attempt + one
   retry with the failure reason attached, exponential backoff between). After two,
   the document is parked with a status and reason. Never a third (§16a).
2. **Layer 2 — transient vs permanent classification.** Transient failures
   (timeout, city 5xx, rate limit, dependency unavailable) are parked and
   **auto-retried next run**. Permanent failures (image-only scan/no text layer,
   schema validation failed twice, malformed PDF) are parked and **never
   auto-retried** — clearing requires a human/code change (§16a). This classifier
   is an invisible-failure surface and gets a property test.
3. **Layer 3 — run circuit breaker.** WHEN more than T4 (proposed 50%) of a run's
   documents fail, THE Pipeline SHALL stop the run, log, and surface it, rather
   than continue spending to be wrong at scale (§16a).
4. **Layer 4 — consecutive-run quarantine.** WHEN one body fails T5 (proposed 3)
   runs in a row, THE Pipeline SHALL quarantine that body: stop attempting it, keep
   serving what is already held, and mark it plainly — NEVER as "late/overdue/
   failed" (§16a, never.md #3). Absence is "not located at [url] as of [timestamp]".
5. **Layer 5 — spend ceiling** (Requirement 6).
6. Politeness backoff on 429/503 is separate from the retry budget — an obligation,
   not a retry (§16a).
7. Retry classification and quarantine decisions are made by CODE, never a model,
   and there is no silent model fallback anywhere in the pipeline (§20f, never.md #7).

### Requirement 6: Spend ledger (§16a layer 5, §18b)

**User Story:** As the project owner, I want an application-level spend ceiling
checked before every run, so that the month's budget cannot be drained silently.

#### Acceptance Criteria

1. THE Pipeline SHALL maintain an application-level spend ledger and SHALL check it
   **before a run starts**; when the envelope is spent, the run does not start
   (§16a layer 5). This is not a cloud budget alert (which only emails).
2. THE monthly model/API spend ceiling SHALL be **T15 = $10/month** (below), and
   it doubles as the §13 auto-dormancy trigger. Aurora's fixed ~$43/month compute
   (R8) is infrastructure, tracked separately, NOT in this model-spend ledger.
   **Arithmetic (shown so the ceiling is trusted, not guessed):**
   - Nova Lite input $0.060/M, output $0.24/M (§27b, verified Aug 22).
   - ~8-page agenda × ~1500 tokens/page = ~12k raw tokens; ×5 for two-pass extract
     + EN rewrite + ES rewrite + verifier re-reads ≈ 60k input + ~4k output/doc ≈
     **$0.0046/document**.
   - ~10 genuinely-new documents/week (conditional GET skips unchanged) ≈ 43/month
     ⇒ **expected steady-state model spend ≈ $0.20/month** (matches §27's ~$0.18).
   - **Ceiling set at $10/month ≈ 50× expected steady-state.** Not the ~255× a $50
     ceiling would give (too loose to catch a runaway). $10 catches a genuine
     runaway — an injection loop or a parser bug re-processing the whole corpus —
     while absorbing the development-iteration spend §27 flags as the real exposure.
3. THE ingestion envelope and the (Spec 4/6) public-search envelope SHALL be
   SEPARATE sub-budgets of T15, so search exhaustion cannot starve ingestion (§18b
   — the availability-via-cost finding): **ingestion sub-budget $7/month (70%),
   search sub-budget $3/month (30%)**. Spec 2 establishes the ingestion sub-budget
   and the separation; search's sub-budget is enforced when search ships.
4. Every run SHALL record its own cost to the ledger, attributable by `run_id`.
5. WHEN the spend ceiling halts a run, THE Pipeline SHALL surface it honestly in
   the run log and raise an alarm, never fail silently or fabricate a result
   (§18b, never.md #7).

### Requirement 7: Run log and observability (§17)

**User Story:** As the operator and as a resident, I want any failure traceable to
a specific run in about a minute, and the run log public later, so that "quiet
because nothing happened" and "quiet because it broke" are never confused.

#### Acceptance Criteria

1. THE Pipeline SHALL generate one `run_id` per run (Spec 0 format) and propagate
   it to every log line, every database row written during the run, every trace,
   and every ledger entry (§17a).
2. Child identifiers SHALL carry the parent `run_id`: `body_id`, `document_id`
   (content-hash), `item_id` (Spec 3), and `agent_invocation_id` (§17a).
3. THE Pipeline SHALL write a persistent run-log record per run: what was read,
   what was skipped because nothing changed, what failed and why, what is
   quarantined, and what it cost (§16c, §17). This record is the data the public
   reading log (Spec 6) renders; Spec 2 produces it.
4. Per-body last-read timestamps SHALL be recorded; a single global last-read
   timestamp is BANNED because it hides exactly the failure a watcher needs to see
   (§16b).
5. Logs SHALL be structured JSON, one event per line, per-component CloudWatch log
   groups `/porchlight/<env>/<component>`, with OTEL traces (§17, Spec 0 logging).
6. Logs SHALL NOT contain packet text (§17, security.md; Spec 0 redaction proven).
7. Alarms SHALL exist for: spend threshold, circuit-breaker trip, body quarantine,
   and zero successful runs in a window (§18b alarms).

### Requirement 8: Database — Aurora Serverless v2 (§33)

**User Story:** As the pipeline, I want a production Postgres with pgvector reached
without a VPC, warm enough that the live watcher never waits, so that storage is
reliable and cheap.

#### Acceptance Criteria

1. THE production database SHALL be Amazon Aurora Serverless v2 PostgreSQL with
   pgvector (§33), replacing Neon.
2. THE cluster minimum capacity SHALL be **0 ACU during development**, raised to
   **0.5 ACU when the live-invoked watcher ships (Spec 5)** or before the demo,
   whichever comes first. Reason: the 0.5 floor exists only for §26c's live watcher,
   where a person waits on a ~15s cold resume; that path does not exist yet. What
   needs the DB today is Spec 2's hourly SCHEDULED run, and a scheduled job absorbs
   a cold resume fine because nobody is watching. This is ~$1/mo instead of ~$44/mo
   for the build. **A Spec 5 task SHALL raise it to 0.5** (one console/IaC setting),
   with this reason recorded so the floor is not silently re-inherited. (§33 amended;
   verified cost: $0.12/ACU-hr in us-east-1 → 0.5 ACU continuous ≈ $43.80/mo.)
3. THE pipeline and site SHALL reach Aurora via the **RDS Data API (HTTPS + IAM)**,
   not a VPC connection, avoiding a NAT gateway (§33).
4. THE schema SHALL cover: meetings, documents, items (Spec 3 populates), events/
   readlog, and the spend ledger (§18 layer 3). Indexes on document hash, meeting
   date, body, and the vector column (§18b point 7).
5. Local development SHALL continue to use docker-compose Postgres+pgvector; the
   same code path SHALL work against both (Spec 0 / §5). Credentials reach Aurora
   only via env/Secrets Manager, never the repo, never an agent (§security).
6. All Aurora resources SHALL carry the four cost tags (§7 requirement carried
   from Spec 0).
7. **The teardown sentence exists before the cluster does** (same rule as Spike B):
   BEFORE the Aurora cluster is created, the README wind-down section SHALL record
   the exact command that removes the cluster and its associated resources, and
   §13's keep/park/take-down list SHALL name Aurora explicitly with its ~$43/month
   always-warm cost (0.5 ACU continuous). An always-warm cluster bills forever, and
   §13 exists because live projects stop being watched.

### Requirement 9: Fail-closed and honest degradation

**User Story:** As a user, I want a degraded pipeline to produce an honest empty
state, never a fabricated or half-done result.

#### Acceptance Criteria

1. WHEN a dependency is degraded, THE Pipeline SHALL fail closed: the honest empty
   state is the answer, never a fabricated or silently-degraded result (§7,
   never.md #7).
2. THE seam between pipeline and site SHALL be the database (§18 layer 2): if the
   pipeline breaks, the site keeps serving what is stored with an honest per-body
   last-read timestamp. Spec 2 guarantees the stored state stays coherent for that.
3. Every `try/except` around a fetch, queue op, or DB write SHALL write to the
   failure log — never a silently swallowed exception (§18b point 6, never.md #12).

### Requirement 10: All fourteen+one thresholds finalized at Spec 2 close

**User Story:** As future maintainer, I want every threshold to carry a final value
and a rationale by the end of this block, so no magic number and no "proposed"
placeholder ships past Spec 2.

#### Acceptance Criteria

1. At Spec 2 close, **every threshold T1–T15 SHALL have a FINAL value and a
   one-line rationale**, each explicitly tagged either "confirmed against measured
   data" or "estimate, unmeasured". **No threshold SHALL carry a "proposed" value
   past this block.** (T15 is the spend ceiling added in R6; T1–T14 are the Spec 1
   R8 / §16a-ii set.)
2. The thresholds Spec 2 owns and must move from OPEN/proposed to final: circuit-
   breaker % (T4), quarantine consecutive-failure count (T5), dormancy threshold
   (T3), monthly spend ceiling (T15). Each with its rationale.
3. THE timeout ordering `T11 < T12 < T14` SHALL be preserved and asserted by a test.

## Pass gate for this block (unchanged from the build plan)

1. **A second run on unchanged data does nothing and says so** — no new records
   written, and the run log states it read and found nothing changed.
2. **A crashed-and-restarted run double-writes nothing** — idempotency holds across
   an interruption.
3. Retry classification (transient vs permanent) correct on real failure examples.
4. Timeout ordering `T11 < T12 < T14` asserted.
5. Aurora reachable via the RDS Data API with pgvector, **min capacity 0 during
   development** (raised to 0.5 at Spec 5), cost-tagged; local docker-compose path
   still works; teardown command + §13 Aurora entry recorded in the README BEFORE
   the cluster is created.
6. Every threshold T1–T15 carries a final value + rationale, tagged measured or
   estimate; none left "proposed" (R10).

## Explicitly out of scope for Spec 2

- Item text extraction, page ranges, the rewrite, any model call (Spec 3).
- The public site, search, and the rendered reading log (Spec 4/6) — Spec 2
  produces the run-log DATA; Spec 6 renders it.
- The watcher and drafts (Spec 5).
- The search public sub-budget's enforcement (Spec 4/6); Spec 2 only establishes
  the separation so ingestion has its own envelope.
