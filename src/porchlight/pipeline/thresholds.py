"""Porch Light — pipeline thresholds, one inspectable place (§16a-ii, Spec 1 R8).

Every value carries a one-line rationale and a MEASURED/ESTIMATE tag (Spec 2 R10:
no threshold ships "proposed"). The timeout ordering constraint T11 < T12 < T14 is
asserted at import time, because a violation there silently re-opens the §20
deadlock (a run that outlives its own lock TTL, or a lock that outlives the
schedule interval).
"""

from __future__ import annotations

# --- Timeouts (seconds), the §20 ordering set ---
# Rationale for each is short; the ORDERING is the load-bearing invariant.
T6_HTTP_FETCH = 30          # ESTIMATE: a ~1MB agenda returns well under this; longer = server struggling.
T7_TOOL_CALL = 45           # ESTIMATE: one hook-wrapped op; above fetch so the fetch's own timeout fires first.
T8_MODEL_CALL = 60          # ESTIMATE: not used in Spec 2 (no model); finalized at Spec 3.
T9_AGENT_INVOCATION = 120   # ESTIMATE: one hunter loop over a body's documents.
T10_PER_DOCUMENT = 90       # ESTIMATE: fetch+hash+classify one doc; above fetch, below agent invocation.
T11_WHOLE_RUN = 600         # 10 min. ESTIMATE: bounds a full pass; must stay under the lock TTL.
T12_LOCK_TTL = 900          # 15 min. ESTIMATE: above run timeout so a live run never loses its lock;
                            #          below schedule interval so a dead/stuck run cannot deadlock the schedule.
T16_LAMBDA_TIMEOUT = 720    # 12 min. ESTIMATE: the scheduler Lambda waits synchronously on a
                            #          run that can take up to T11 (10m). Must exceed T11 so it does
                            #          not abandon a healthy run (orphaning a lock), and stay under
                            #          T12 so a hung hunter cannot pin the Lambda past the lock TTL.
T14_SCHEDULE_INTERVAL = 3600  # 60 min. MEASURED-adjacent: hourly per §7 good-citizen posture; > lock TTL.

# --- Retry / quarantine / dormancy (§16a) ---
T1_HORIZON_FUTURE_DAYS = 30   # ESTIMATE: realistic scheduling lead time; posting lead measured at ~5d median (§35e).
T2_HORIZON_PAST_DAYS = 14     # ESTIMATE: catches an agenda amended shortly after its meeting.
T3_DORMANCY_HOURS = 36        # ESTIMATE: beyond ~1.5 days the quiet-vs-broken ambiguity must resolve to broken (§16b).
T4_CIRCUIT_BREAKER_PCT = 50   # ESTIMATE: half a body's docs failing signals a site-side problem, not one bad file.
T5_QUARANTINE_RUNS = 3        # ESTIMATE: three strikes separates a blip from a genuinely broken body.
T13_MAX_DOCS_PER_BODY = 50    # ESTIMATE: far above any real per-run count; a runaway past this is a parsing bug.
ATTEMPTS_PER_DOCUMENT = 2     # SET (§16a L1): one retry, then park. Never a third.

# --- Spend (§16a L5, §18b), model/API only; Aurora infra is NOT here ---
T15_SPEND_CEILING_USD = 10.0        # COMPUTED: ~50x the ~$0.20/mo measured steady-state (arithmetic in Spec 2 R6.2).
INGESTION_SUBBUDGET_USD = 7.0       # 70% of T15.
SEARCH_SUBBUDGET_USD = 3.0          # 30% of T15 (enforced at Spec 4/6).

# --- Ordering invariant: the §20 guard. Violating this is a deadlock bug. ---
# Full chain: run timeout < Lambda timeout < lock TTL < schedule interval.
# - run < Lambda: the scheduler Lambda must outlast a healthy run, or it abandons
#   one and orphans a held lock.
# - Lambda < lock TTL: a hung hunter must not pin the Lambda past the lock TTL.
# - lock TTL < schedule: a stuck run's lock must expire before the next trigger.
assert T11_WHOLE_RUN < T16_LAMBDA_TIMEOUT < T12_LOCK_TTL < T14_SCHEDULE_INTERVAL, (
    "Timeout ordering violated: require run < Lambda < lock TTL < schedule "
    f"(got {T11_WHOLE_RUN} < {T16_LAMBDA_TIMEOUT} < {T12_LOCK_TTL} < {T14_SCHEDULE_INTERVAL}). "
    "A run must not outlive the Lambda waiting on it, the Lambda must not outlive "
    "the lock TTL, and a stuck run's lock must expire before the schedule fires again (§20)."
)
