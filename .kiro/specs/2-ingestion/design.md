# Design Document — Spec 2: Ingestion

## Scope

The orchestration layer that runs the Spec 1 adapter hourly, safely, within
budget: EventBridge schedule, run lock (TTL + heartbeat), in-process work list
with per-document status, content-hash change detection, the five-layer retry
budget, the application spend ledger, the run log, observability, and the Aurora
Serverless v2 database + schema. No item extraction, no model, no public site.

References §7, §16a, §17, §18/§18b, §20, §33. The rigor budget (working rigor +
property tests on idempotency and retry-classification) and pass gate are settled
in requirements.md and not restated. R4's queue is STUB by decision — the
machinery matches the workload (§32c): ~15 in-horizon meetings, ~35 fetches, max
1 concurrent, ~90 seconds, one process.

## Module layout (structure.md: one file, one responsibility)

```
pipeline/
  run.py           # entrypoint: acquire lock → build work list → process → record run log → release
  lock.py          # run lock: acquire, heartbeat, TTL expiry, release, interrupted-status
  worklist.py      # in-process ordered work list over in-horizon documents (R4)
  status.py        # per-document status transitions (pending/in_flight/done/parked/permanent_fail)
  retry.py         # five-layer retry budget: attempt cap, transient/permanent classify, circuit breaker, quarantine
  ledger.py        # spend ledger: check-before-run, record-per-run, sub-budgets
  runlog.py        # per-run + per-body run-log records (the data Spec 6 renders)
db/
  schema.sql       # meetings, documents, items, events/readlog, spend_ledger, run_lock, body_status
  migrations/      # forward migrations
  data_api.py      # RDS Data API client wrapper (HTTPS+IAM); same interface over local docker Postgres
  init/            # (exists) local pgvector extensions
```

`db/data_api.py` is the single seam that lets the same pipeline code run against
Aurora (RDS Data API in prod) and docker-compose Postgres (local). Everything
above it is storage-backend-agnostic.

## Run lifecycle (run.py)

```
scheduled trigger (EventBridge, hourly)
  │
  ├─ ledger.check_before_run()  ── envelope spent? → do not start; log; alarm  (R6.1)
  │
  ├─ lock.acquire(run_id, ttl=T12)  ── held by live run? → exit without starting (R2.1)
  │        │ heartbeat thread refreshes lock while alive (R2.3)
  │
  ├─ fetch combined index (Spec 1 fetch, 1 request) → enumerate_meetings()
  │
  ├─ horizon.in_horizon() gate  ── keep only in-window meetings BEFORE any per-meeting fetch (Spec 1 R4.3)
  │
  ├─ worklist = deterministic order of in-horizon documents (R4.1)
  │     for each document (concurrency 1):
  │        status: pending → in_flight
  │        conditional GET (Last-Modified/ETag)
  │           304 unchanged  → status done, NO new record (R3.2 idempotency)
  │           200 changed    → content-hash → new/changed? → write doc row (idempotent on hash)
  │        on failure → retry.classify() → parked (transient) | permanent_fail
  │        circuit breaker: if run failure % > T4 → stop run, log, surface (R5.3)
  │
  ├─ per-body: update last-read timestamp; quarantine check (T5 consecutive failures) (R5.4, R7.4)
  │
  ├─ runlog.write(run_id, read/skipped/failed/quarantined/cost)  (R7.3)
  ├─ ledger.record(run_id, cost)  (R6.4)
  └─ lock.release()   (on SIGTERM/reclaim: release + status=interrupted)  (R2.5)
```

## Run lock (lock.py) — the §20 deadlock finding

A DB row (`run_lock`) is the lock, not an in-memory flag, so it survives process
death and is visible to the next trigger.

- `acquire(run_id)`: atomic insert-or-take-if-expired. Row carries `run_id`,
  `acquired_at`, `heartbeat_at`, `ttl_seconds`. Acquire succeeds iff no row, or
  the existing row's `heartbeat_at + ttl < now` (the held lock is stale/dead).
- `heartbeat()`: a background thread updates `heartbeat_at` every ~T12/3 while the
  run is alive, so a long-but-healthy run keeps its lock (R2.3). **The heartbeat is
  CAPPED: it never refreshes past `acquired_at + T11` (10m).**
- `release()`: delete the row. On SIGTERM, release and mark the run `interrupted`.
- **Ordering asserted in code and test:** `T11 (run 10m) < T12 (lock TTL 15m) <
  T14 (schedule 60m)` (R2.4). A dead run's lock expires (15m) before the next-next
  trigger; a healthy run (≤10m) keeps its lock via heartbeat.
- **The stuck-but-alive case (§20 returning through a side door).** A naive
  heartbeat that refreshes "while the process is alive" does NOT cover a run whose
  main thread is blocked on a socket that never returns: the heartbeat thread would
  refresh forever, the TTL would never fire, and the watch would be silently dead
  with no alarm. Stuck is more common than dead. Fix: **the heartbeat stops
  refreshing once wall-clock exceeds `acquired_at + T11`, regardless of process
  liveness.** So a hung run's lock still expires at T12 and the next trigger
  recovers, and T11 becomes a real wall-clock deadline, not an aspiration.
- When the main run notices it has passed T11, it stops work, marks the run
  **`timed_out`** (a status distinct from `failed` and `interrupted`), and writes
  the run log.
- Stale-lock detection raises an alarm (R2.6) — including the stuck-run case, where
  the lock goes stale at T12 while the process may still be technically alive.

Why a DB lock, not SQS/Redis/DynamoDB-lock: one process, hourly, Aurora already
present. A DB row with TTL+heartbeat is the least machinery that meets the
deadlock requirement.

## Change detection and idempotency (R3) — the pass gate

- Conditional GET first (Spec 1 fetch): a `304` means unchanged → mark the
  document `done`, write nothing new. This is most documents on most runs — but
  NOT guaranteed (§39): the city batch-touched all 152 files to one `Last-Modified`,
  so on a re-index run every document returns 200 and re-downloads. Conditional GET
  is an optimization whose savings can vanish; the content hash below is what keeps
  the result correct regardless. A re-index run costs bandwidth, not correctness.
- On `200`: compute `document_id = sha256(bytes)` (Spec 1 hash). Upsert keyed on
  `document_id`. If the id already exists, it is the same bytes → no new row, no
  downstream work (R3.2).
- **Crash-restart safety (pass gate 2):** the `documents` row and the per-document
  `status` are written in the same transaction as the work that produced them.
  A restart reads status: `done`/`permanent_fail` are skipped, `in_flight` is
  re-driven (idempotent because the upsert is keyed on content hash), `pending` is
  processed. Running twice over the same fixed input ⇒ identical stored state
  (R3.4, property test).
- **Second-run-does-nothing (pass gate 1):** with all docs `done` and unchanged,
  every conditional GET returns 304, no rows are written, and the run log records
  "read N, changed 0".

## In-process work list and status (R4) — queue is STUB

- `worklist.build(in_horizon_meetings)` returns documents in a deterministic order
  (by meeting date, then meeting id, then document role) so re-runs are stable.
- `status` column on `documents`: `pending → in_flight → done`, or `→ parked`
  (transient, auto-retry next run) or `→ permanent_fail` (never auto-retry).
- Concurrency 1 (Spec 1 fetch lock).
- **STUB comment in run.py:** "SQS with visibility timeout + DLQ is the v2 work
  distribution path. Build it only when: (a) more than one city, or (b) a run no
  longer fits in one process within T11. Until then an in-process ordered list +
  DB status is correct and has fewer failure modes." No queue provisioned.

## Five-layer retry budget (retry.py) — §16a

- **L1 attempts=2:** attempt, then one retry with the failure reason attached,
  exponential backoff between; then park. Never a third.
- **L2 classify(failure) → transient | permanent** (invisible-failure surface →
  property test): transient = timeout, city 5xx, 429, dependency-unavailable →
  `parked`, auto-retried next run. permanent = image-only/no-text-layer, schema
  fail ×2, malformed PDF → `permanent_fail`, never auto-retried.
- **L3 circuit breaker:** if `failed/attempted > T4` in one run, stop the run.
- **L4 quarantine:** if a body fails `T5` consecutive runs, mark `body_status`
  quarantined; keep serving stored data; mark plainly — never "late/overdue/
  failed" (never.md #3); absence is "not located at [url] as of [timestamp]".
- **L5 spend ceiling:** ledger.check_before_run (R6).
- All decisions are CODE. No model in this path; no silent model fallback (§20f).
- Politeness 429/503 backoff is separate (Spec 1 fetch), not a retry attempt.

## Spend ledger (ledger.py) — §16a L5, §18b

- `spend_ledger` table: append-only rows `(run_id, component, cost_usd, ts)`.
- `check_before_run(sub_budget)`: sum current-month cost for the sub-budget; if
  `>= sub_budget`, the run does not start (R6.1), logs, alarms.
- Sub-budgets of **T15 = $10/mo**: ingestion **$7 (70%)**, search **$3 (30%)**
  (R6.3). Spec 2 enforces the ingestion sub-budget; search's is wired at Spec 4/6.
- Aurora's ~$43/mo fixed compute is infrastructure, tracked in §13, NOT in this
  model-spend ledger (R6.2). The ledger is model/API spend only.
- **`ledger.py` docstring SHALL say so explicitly**, because the file is named the
  spend ledger with a $10 ceiling and someone reading it at midnight in three weeks
  will otherwise take $10 for the monthly bill: "This ledger covers model and API
  spend only. Aurora Serverless v2 fixed compute (~$43/mo at 0.5 ACU) is
  infrastructure, tracked in §13's wind-down list, and is NOT bounded by T15." The
  same sentence goes in the README cost section.
- Every run records its cost attributable by `run_id` (R6.4). Spec 2 has no model
  calls, so ingestion-run cost is ~fetch/DB only (near zero); the ledger and the
  check exist now so Spec 3's model spend lands in a ready envelope.

## Run log and observability (runlog.py) — §17

- `readlog` table: one row per run with `run_id`, started/finished, counts
  (read / skipped-unchanged / failed / quarantined), and cost. Per-body rows carry
  `body_id` + last-read timestamp — **no single global last-read** (R7.4).
- `run_id` (Spec 0 format) on every log line, every row written this run, every
  ledger entry, every trace (R7.1). Child ids carry the parent (R7.2).
- Structured JSON logs, OTEL traces (R7.5); logs never carry packet text (R7.6,
  Spec 0 redaction proven in the runtime).
- **Log group naming — two regimes, because §31b found we do not control all of
  them.** Do not assume `/porchlight/<env>/<component>` everywhere:
  - **Components we provision** (the Spec 2 pipeline: the EventBridge-triggered
    ingestion runner and its Lambda/compute) → we set the group name
    `/porchlight/<env>/<component>` explicitly.
  - **AgentCore-managed runtimes** (the Spec 3+ agents) → AgentCore auto-names the
    group and we do NOT control it; the discriminator is the `component` field in
    the JSON payload (§31b, proven at Spike B). Filter by `component`, not group
    name, there.
  - Spec 2 components fall on the **provisioned** side (hunter-adjacent ingestion
    runs on our compute, not inside an AgentCore runtime), so Spec 2's groups are
    `/porchlight/<env>/ingestion`. The `component` field is still on every line so
    cross-regime queries work uniformly.
- Alarms: spend threshold, circuit-breaker trip, body quarantine, zero successful
  runs in a window (R7.7).

## Database — Aurora Serverless v2 (R8, §33)

- Aurora Serverless v2 PostgreSQL, pgvector, **min capacity 0.5 ACU (not 0)** so
  the §26c live watcher never waits on a ~15s cold resume.
- Access via **RDS Data API (HTTPS + IAM)** — no VPC, no NAT gateway. `db/data_api.py`
  wraps it behind the same interface the local docker Postgres path uses, so
  pipeline code is backend-agnostic (R8.5).
- Schema (`db/schema.sql`): `meetings`, `documents` (with `status`, `document_id`
  hash, `body_id`, `meeting_date`), `items` (Spec 3 populates), `readlog`,
  `spend_ledger`, `run_lock`, `body_status`. Indexes on document hash, meeting
  date, body, and the vector column (R8.4, §18b#7).
- Credentials via env / Secrets Manager only — never repo, never an agent
  (§security). All resources cost-tagged (R8.6).
- **Teardown-before-create (R8.7):** before `terraform/agentcore/console` creates
  the cluster, the README wind-down section records the exact destroy command and
  §13's keep/park/take-down list names Aurora with its ~$43/mo cost. The sentence
  exists before the resource, same as Spike B.

## Thresholds finalized at close (R10)

Spec 2 sets final values for the ones it owns (each tagged measured/estimate):
- T3 dormancy: **36h** (estimate — beyond ~1.5 days the quiet-vs-broken ambiguity
  must resolve to broken; §16b).
- T4 circuit breaker: **50%** (estimate — half a body's docs failing signals a
  site-side problem, not one bad file).
- T5 quarantine: **3 consecutive runs** (estimate — three strikes separates a blip
  from a genuinely broken body).
- T15 spend ceiling: **$10/mo** (computed — ~50× the ~$0.20/mo expected model
  spend; arithmetic in requirements R6.2).
- T11<T12<T14 preserved and asserted.

## Error handling / fail-closed (R9)

- Degraded dependency → honest empty state, never fabricated (never.md #7).
- The DB is the pipeline↔site seam: a broken pipeline leaves the site serving
  stored data with honest per-body last-read timestamps.
- Every try/except around a fetch, DB op, or transition writes to the failure log
  (never.md #12).

## Testing (rigor budget)

**Property tests (invisible-failure surfaces):**
- Idempotency: run twice over a fixed fixture ⇒ identical stored state (R3.4).
- Retry classify(failure) → transient/permanent is total and stable (R5.2).

**Working-rigor tests:**
- Second run on unchanged data writes no rows and logs "changed 0" (pass gate 1).
- Simulated crash mid-run (kill after some docs `done`) then restart double-writes
  nothing (pass gate 2), via the status column + hash upsert.
- Lock: a stale (expired-heartbeat) lock is reclaimable; a fresh one is not;
  `T11<T12<T14` asserted (pass gate 4).
- **Stuck-but-alive lock (the §20 side-door case):** a run that exceeds T11 stops
  heartbeating even with the process still running, its lock becomes reclaimable at
  T12, the stale-lock alarm fires, and the run is marked `timed_out` (distinct from
  `failed`/`interrupted`). This is the highest-value lock test.
- Circuit breaker trips at T4; quarantine at T5; both surface in the run log.
- Ledger: check_before_run refuses to start when the sub-budget is spent.
- Aurora reachability is a live/marked check (RDS Data API, pgvector present,
  0.5 ACU, cost tags), skipped when the cluster env is unset (Spec 0 smoke pattern).

## Explicitly out of scope

Item extraction / page ranges / rewrite / any model call (Spec 3); the public site
and rendered reading log (Spec 6); the watcher and drafts (Spec 5); enforcing the
search sub-budget (Spec 4/6). Spec 2 produces the run-log data and the ready
spend envelope; later specs consume them.
