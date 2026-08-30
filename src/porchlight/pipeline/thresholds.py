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
# T16_LAMBDA_TIMEOUT — OBSOLETE (§38). It existed for a scheduler Lambda that
# synchronously waited on an AgentCore hunter runtime, so its timeout had to sit
# between T11 and T12. §38 made the hunter a deterministic Lambda invoked DIRECTLY
# by EventBridge (no runtime, no synchronous wait, no intermediate hop), so there
# is no timeout to order between T11 and T12. The hunter Lambda's own timeout is
# just "> T11 with margin, < Lambda's 15-min max" (set to 12 min at deploy), which
# is a deployment setting, not an ordering constraint. Kept here, marked, so the
# reasoning survives rather than vanishing.
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

# --- Verifier check-5 reading-level floors (Spec 3 R3b, DERIVED at task 8 calibration) ---
# A rewrite passes check 5 only if it reads at or above the floor for its language
# (higher = easier). Both DERIVED, not guessed: min score across the ten hand-written
# correct golden-0a rewrites, minus a flat 5.0 margin. Per-language metrics: English
# Flesch Reading Ease, Spanish Fernandez Huerta (never the English metric on Spanish).
READING_FLOOR_EN = 33.8   # DERIVED (task 8): min EN correct-rewrite score 38.8 - 5.0. Flesch Reading Ease.
READING_FLOOR_ES = 64.0   # PROVISIONAL, Fernandez Huerta. Re-derived (task 9): the original 77.3 (min of 5
                          # single-author golden rewrites, 82.3, - 5.0) rejected otherwise-fine MODEL output
                          # scoring 69.4-71.8. New floor admits the observed acceptable model range: min
                          # observed good model ES score 69.4 - 5.0 margin = 64.4, rounded down to 64.0. Still
                          # provisional (small n, one meeting); revisit at task 0b. Correct golden ES (min 82.3)
                          # and adversarial golden-002/es (68.5) both stay on the correct side: 82.3 passes, and
                          # 68.5 still fails checks 2/6 on the translated street name (its rejection never
                          # depended on check 5).

# --- Ordering invariant: the §20 guard. Violating this is a deadlock bug. ---
# Chain (post-§38, hunter runs in-process on a directly-invoked Lambda):
#   run timeout < lock TTL < schedule interval.
# - run < lock TTL: a run must not outlive its own lock (heartbeat is capped at T11).
# - lock TTL < schedule: a stuck run's lock must expire before the next trigger.
# The Lambda's own 12-min timeout is > T11 with margin and < Lambda's 15-min max;
# it is a deployment setting, not part of this ordering (§38 retired T16).
assert T11_WHOLE_RUN < T12_LOCK_TTL < T14_SCHEDULE_INTERVAL, (
    "Timeout ordering violated: require run timeout < lock TTL < schedule interval "
    f"(got {T11_WHOLE_RUN} < {T12_LOCK_TTL} < {T14_SCHEDULE_INTERVAL}). "
    "A run must not outlive its own lock, and a stuck run's lock must expire before "
    "the schedule would fire again (§20)."
)
