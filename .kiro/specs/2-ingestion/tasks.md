# Implementation Plan: Spec 2 — Ingestion

## Overview

Build the orchestration layer that runs the Spec 1 adapter hourly, safely, within
budget. References §7, §16a, §17, §18/§18b, §20, §33, and the approved
requirements/design.

Ordering rationale:
- **The Aurora teardown line and the schema come BEFORE any cluster is created**
  (R8.7, same rule as Spike B: the destroy sentence exists before the resource).
- **The run lock is built and tested EARLY, including the stuck-but-alive case.**
  The lock is where a subtle bug costs the most and shows the least (§20 twice
  already). It is exercised against local Postgres before Aurora exists.
- Pure/DB-local logic first (schema, lock, status, retry classify, ledger, change
  detection) — all testable against docker-compose Postgres with no cloud. Cluster
  creation (a billable resource) is a PROPOSE-and-wait task near the end.

Rigor budget (style.md): working rigor + property tests on the two invisible
surfaces (idempotency, retry classification). Pass gate is behavioral (R pass
gate 1–6). Tags: [PERMANENT] ships in `pipeline/` or `db/`. [TEST]. [VERIFICATION].
[INFRA-PROPOSE] = creates a billable/external resource, requires approval first.

## Tasks

- [x] 0. Wind-down sentences before the resources (R8.7) [PERMANENT]
  - [x] 0.1 Record teardown commands + §13 entries in the README BEFORE the resources exist
    - Done. README Wind-down section: EventBridge schedule teardown FIRST (disable+delete, reason: stopping the crawler is the real obligation), then Aurora cluster teardown (~$43/mo). README Cost section: ledger-covers-model-only / Aurora-is-infra sentence. All written before any resource exists.
    - **EventBridge schedule, named FIRST in §13 (above Aurora):** the exact command to disable and delete the schedule, with the reason stated plainly — this is the thing that touches someone else's server, so for a trustworthy-reader product the wind-down obligation is STOPPING, not cost. A forgotten crawler hitting a public body hourly is a broken promise in a way a forgotten DB bill is not.
    - Aurora: exact command to delete the cluster and associated resources; §13 entry with ~$43/mo (0.5 ACU continuous).
    - README cost section: the ledger-covers-model-only / Aurora-is-infra sentence (design §ledger).
    - _Requirements: 8.7, 6.2_

- [x] 1. Database schema (local first, backend-agnostic) [PERMANENT]
  - [x] 1.1 Write `db/schema.sql`: bodies, meetings, documents (status, document_id hash, body_id, meeting_date), items (Spec 3 fills), readlog, spend_ledger, run_lock, body_status
    - Done. 8 tables. Indexes on document status/meeting/hash-PK, meeting date+body, ledger. Vector column declared; vector INDEX deferred to Spec 4 (dim not yet fixed) with a note. readlog.status includes `timed_out` (design correction). body_status is per-body last-read only (no global).
    - _Requirements: 8.4_
  - [x] 1.2 `db/data_api.py`: one interface over RDS Data API (prod) and docker Postgres (local)
    - Done. `get_backend()` selects by config (Aurora ARNs → Data API; else DATABASE_URL → local psycopg; else raises — never a silent default). Parameterized only. boto3/psycopg lazy-imported.
    - _Requirements: 8.5_
  - [x] 1.3 Apply schema to local docker-compose Postgres; verify tables + indexes + pgvector
    - RESULT: 8 tables created, 6 idx_ indexes present, pgvector present, parameterized round-trip works through the wrapper. GOTCHA noted: literal `%` in SQL (e.g. `LIKE 'x%'`) must be `%%` or parameterized under psycopg — a wrapper caveat for callers.
    - _Requirements: 8.4, 8.5_

- [x] 2. Run lock — built and tested EARLY (the highest-risk piece) [PERMANENT]
  - [x] 2.1 Implement `pipeline/lock.py`: acquire (insert-or-take-if-expired), heartbeat (capped at acquired_at + T11), release, timed_out/interrupted statuses
    - Done. DB-row lock via injected backend. Heartbeat thread refuses to refresh past `acquired_at + T11`; `check_deadline()` raises `RunTimedOut`. `thresholds.py` added with T1–T15 (each rationale + measured/estimate) and the T11<T12<T14 invariant asserted at import.
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_
  - [x] 2.2 Lock tests incl. the stuck-run case [TEST]
    - Done. 6 tests: acquire/release, held-lock rejects second, expired reclaimable, fresh not reclaimable, ordering invariant, and the stuck-but-alive case (run past T11 → RunTimedOut + lock reclaimable at T12 though process lives). All pass against local Postgres; skip cleanly when DATABASE_URL unset (57 passed, 6 skipped).
    - _Requirements: 2.2, 2.3, 2.4, 2.6_

- [ ] 3. Per-document status + in-process work list (queue is STUB) [PERMANENT]
  - [ ] 3.1 Implement `pipeline/status.py` (pending/in_flight/done/parked/permanent_fail) and `pipeline/worklist.py` (deterministic order)
    - STUB comment in run.py: SQS+visibility+DLQ is v2, built only at >1 city or a run exceeding one process within T11.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 4. Change detection and idempotency [PERMANENT]
  - [ ] 4.1 Wire conditional GET (304 → done, no write) + content-hash upsert (same bytes → no new row), status written in the same transaction as the work
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ] 4.2 Property test: idempotency [TEST]
    - **Property: running twice over a fixed fixture yields identical stored state (R3.4).**
    - Tag: `# Feature: 2-ingestion, Property 1: idempotency`
    - _Requirements: 3.4_

- [ ] 5. Five-layer retry budget [PERMANENT]
  - [ ] 5.1 Implement `pipeline/retry.py`: L1 attempts=2; L2 classify transient/permanent; L3 circuit breaker (T4); L4 quarantine (T5). Code-only, no model, no silent fallback.
    - Quarantine marks a body plainly, never "late/overdue/failed"; absence string is the §16b form.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7_
  - [ ] 5.2 Property test: transient/permanent classification is total and stable [TEST]
    - Tag: `# Feature: 2-ingestion, Property 2: retry classification`
    - _Requirements: 5.2_

- [ ] 6. Spend ledger [PERMANENT]
  - [ ] 6.1 Implement `pipeline/ledger.py`: append-only rows, check_before_run(sub_budget), record(run_id, cost)
    - Docstring: covers model/API spend ONLY; Aurora ~$43/mo is infra (§13), NOT bounded by T15.
    - Sub-budgets of T15=$10: ingestion $7 (70%), search $3 (30%, enforced Spec 4/6).
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [ ] 6.2 Test: run does not start when the ingestion sub-budget is spent [TEST]
    - _Requirements: 6.1_

- [ ] 7. Run log + observability [PERMANENT]
  - [ ] 7.1 Implement `pipeline/runlog.py`: per-run + per-body records (counts, cost); per-body last-read timestamps, NO global last-read
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [ ] 7.2 Wire logging + log-group regimes (§31b): provisioned components → `/porchlight/<env>/ingestion`; AgentCore runtimes filter by `component` field
    - Logs never carry packet text (Spec 0 redaction); alarms: spend, circuit breaker, quarantine, zero-successful-runs.
    - _Requirements: 7.5, 7.6, 7.7_

- [ ] 8. Run entrypoint (compose it all) [PERMANENT]
  - [ ] 8.1 Implement `pipeline/run.py`: ledger-check → lock → enumerate → horizon gate → worklist → per-doc process → circuit breaker → per-body quarantine/last-read → runlog → ledger record → release
    - Fail-closed on degraded dependency; every try/except writes the failure log.
    - _Requirements: 9.1, 9.2, 9.3, 1.3, 1.4_

- [ ] 9. Behavioral pass-gate tests (against local Postgres) [TEST]
  - [ ] 9.1 Second run on unchanged data writes no rows and logs "changed 0" (pass gate 1)
    - _Requirements: pass gate 1_
  - [ ] 9.2 Crash mid-run (kill after some docs done) → restart double-writes nothing (pass gate 2)
    - _Requirements: pass gate 2, 3.3_

- [x] 10.0 INFRA-PROPOSE: deploy the hunter as a Lambda (§38, was AgentCore) [INFRA-PROPOSE]
  - [x] 10.0.1 Deploy `run.py` + Spec 1 adapter + `db/` as the `porchlight-dev-hunter` Lambda
    - Done. Lambda `porchlight-dev-hunter`, **python3.14** (matches §30a — corrected from an initial 3.13), 12-min timeout, scoped role `porchlight-dev-hunter-role` (rds-data on the cluster, read RDS-managed secret, CloudWatch logs), default networking, four cost tags. Handler runs `run_ingestion` in-process.
    - RESULT (proven by controlled manual invokes; schedule still disabled): clean run `status=ok`, 21 bodies seeded, 11 in-horizon meetings, 15 documents recorded, readlog ok. Second invoke: read=0, skipped=15, documents still 15 — **pass gates 1 (second run does nothing) and idempotency proven LIVE against Aurora.**
    - Deploy findings (all fixed, see wip + fix commits): Aurora cold-resume needed a ~90s bounded retry (min-cap 0 fully-paused resume); Data API needs explicit `::timestamptz` casts (psycopg doesn't); the pipeline had to seed bodies+meetings before the FK'd children (the fresh-schema test now guards it, testing.md #4); relative worklist URLs made absolute.
    - _Requirements: §38 compute-target; 26 topology; pass gate 1, 2, 3_

- [x] 10. Schedule wiring (EventBridge, direct target) [INFRA-PROPOSE]
  - [x] 10.1 Create the EventBridge hourly schedule **DISABLED**, target = the hunter Lambda DIRECTLY (§38, no scheduler-Lambda hop)
    - Done. `porchlight-dev-ingestion`, `rate(1 hour)`, **State=DISABLED** (verified), target = hunter Lambda, `FlexibleTimeWindow=OFF` (no catch-up). Invoke role `porchlight-dev-scheduler-invoke-role` scoped to `lambda:InvokeFunction` on that one function only.
    - FINDING (tagging, §31e-class): EventBridge **schedules do not carry resource tags individually** — tags attach to the schedule GROUP. The `default` group is tagged with the four cost tags instead. Recorded, not silently skipped. The schedule fires nothing until enabled at task 13.
    - _Requirements: 1.1, 1.2, 1.4, 7 tagging_
    - **Ships disabled and why:** an enabled schedule would fire hourly against the City of Ventura's servers before Aurora (wave 7) and the pass gates (wave 8) exist. It is created disabled and only enabled in task 13 after every gate is met. Record this in tasks.md/README.
    - _Requirements: 1.1, 1.2, 1.4_

- [x] 11. Thresholds finalized (R10) [PERMANENT]
  - [x] 11.1 Every T1–T15 has a FINAL value + rationale, tagged measured or estimate; none left "proposed"
    - Done in `src/porchlight/pipeline/thresholds.py` (single inspectable place), T11<T12<T14 asserted at import. Final table:
      - T1 horizon future 30d (estimate); T2 horizon past 14d (estimate)
      - T3 dormancy 36h (estimate); T4 circuit breaker 50% (estimate); T5 quarantine 3 runs (estimate)
      - T6 fetch 30s, T7 tool 45s, T8 model 60s (estimate; finalized Spec 3), T9 agent 120s, T10 per-doc 90s (all estimate)
      - T11 run 600s, T12 lock TTL 900s, T14 schedule 3600s (estimate; ordering asserted)
      - T13 max docs/body 50 (estimate)
      - T15 spend ceiling $10/mo (COMPUTED, ~50x measured $0.20/mo); ingestion $7 / search $3
      - Attempts/document 2 (set, §16a L1)
    - Posting lead time itself is MEASURED (median 5d, min 0d, §35e) and informs T1/T14 but is not a stored threshold.
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 12. INFRA-PROPOSE: create Aurora Serverless v2 (billable) [INFRA-PROPOSE]
  - [x] 12.1 PROPOSE before acting: cluster creation spends money / creates persistent external state
    - Preconditions verified present: task 0.1 teardown line recorded; schema (task 1) ready; local path green.
    - Create Aurora Serverless v2 + pgvector, **min capacity 0** (dev; raised to 0.5 at Spec 5), RDS Data API (no VPC), cost tags. Verify pgvector + reachability. Create the Secrets Manager secret for Data API creds.
    - RESULT: cluster `porchlight-dev` (aurora-postgresql 16.9), instance `porchlight-dev-instance` (db.serverless), both available. Data API enabled. RDS-managed secret `rds!cluster-b1413d42-...`. MinCapacity 0.0 / Max 1.0, auto-pause 300s. vector+pg_trgm+unaccent present. Schema (8 tables) applied via the Data API using data_api.py's Aurora path; parameterized round-trip verified. Four cost tags verified on the cluster (not assumed). Pass gate 5 met.
    - _Requirements: 8.1, 8.2, 8.3, 8.6_
  - [x] 12.2 Leave a re-runnable Aurora smoke test (§28b) [TEST]
    - `tests/live/test_smoke_aurora.py`, `@pytest.mark.live`, excluded from default, part of `make smoke`.
    - Skips ONLY when the Aurora endpoint env var is unset; FAILS on any error from a cluster that exists (same skip-vs-fail discipline as Spec 0).
    - Asserts: a real Data API query returns; pgvector present; **min capacity 0** (the dev setting — asserts it did NOT silently inherit 0.5); the four cost tags on the cluster.
    - RESULT: 4 tests pass against the live cluster; skip cleanly when AURORA_CLUSTER_ARN unset.
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

- [ ] 13. Final checkpoint + enable the schedule
  - All property + working-rigor tests pass. Pass gates 1–6 met. Thresholds all final. Aurora teardown line recorded before creation. Ledger docstring + README cost sentence present. Log-group regimes correct. Aurora smoke test (12.2) green.
  - **ONLY after all of the above: enable the EventBridge schedule** (created disabled in 10.1). This is the single action that starts hourly traffic against the city; it is the last thing done, deliberately.
  - _Requirements: pass gate 1–6, 10.1_

## Notes

- The lock is deliberately first-and-tested-early: §20 has bitten twice (deadlock,
  then the heartbeat side-door). A subtle lock bug costs the most and shows the least.
- Aurora creation (task 12) is the only billable step and is PROPOSE-and-wait.
  Everything else runs against local docker-compose Postgres.
- Property tests: `# Feature: 2-ingestion, Property {N}: {title}`.
- No model calls in Spec 2; the ledger exists so Spec 3's model spend lands in a
  ready, bounded envelope.

### Forward flags (recorded here, owned by later specs — do not build in Spec 2)

- **Spec 5 — raise Aurora min capacity 0 → 0.5 ACU.** The 0.5 floor is for §26c's
  live-invoked watcher (a person waiting on a ~15s cold resume). During dev the DB
  is only hit by the hourly scheduled run, which absorbs a cold resume fine, so it
  runs at min capacity 0 (~$4–5/mo est.) and is raised to 0.5 (~$44/mo) when the
  watcher ships or before the demo. One console/IaC setting. Reason recorded so the
  floor is not silently re-inherited. (§33 amended.)
- **Spec 3 — measure real infra cost.** Read actual monthly cost from Cost Explorer
  filtered by the four tags after ~a week of real runs; replace the README's
  ~$4–5/mo Aurora ESTIMATE with the measured figure.
- **§30d flag RETIRED (§38).** The hunter is a deterministic Lambda, not an
  AgentCore runtime, so the "hunter and extractor need opposite networkMode on
  separate runtimes" problem dissolves. Only the extractor and watcher live on
  AgentCore. Spec 3 note updated: the extractor runtime has no egress (§30d); the
  hunter's egress lives on Lambda, entirely separate.
- **Hunter Lambda error behavior (§38):** the hunter runs IN-PROCESS in the Lambda
  (no InvokeAgentRuntime hop). On any unhandled error it logs and exits non-zero; it
  does NOT retry — the run lock + next hourly trigger handle recovery. Lambda
  timeout 12 min (> T11 with margin, < Lambda's 15-min max); this is a deployment
  setting, not an ordering constraint (T16 retired).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["4.1", "5.1", "6.1"] },
    { "id": 4, "tasks": ["4.2", "5.2", "6.2", "7.1"] },
    { "id": 5, "tasks": ["7.2", "8.1"] },
    { "id": 6, "tasks": ["9.1", "9.2", "10.1", "11.1"] },
    { "id": 7, "tasks": ["12.1", "12.2"] },
    { "id": 8, "tasks": ["13"] }
  ]
}
```
