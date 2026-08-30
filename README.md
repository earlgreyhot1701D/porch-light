# Porch Light

An agent that watches a city's public meeting agendas on behalf of one person, summarizes matches in English and Spanish with a receipt on every claim, and drafts the structure of a public comment that only the human can finish and send.

**Hackathon:** AWS Agents for Humans (Good Neighbor track). Submission deadline: Sep 13, 2026.

## Disclosure

A prior weekend prototype of this idea exists at github.com/earlgreyhot1701D/civiq; none of its code is used here.

## Stack

- **Language:** Python
- **Agent framework:** Strands Agents SDK — version: 1.53.0
- **Deployment:** the two agents (extractor, watcher) run on Bedrock AgentCore (direct code deploy, .zip, no container); the deterministic hunter runs as an EventBridge-scheduled Lambda (§38); frontend + read-only API on Vercel
- **Database:** Amazon Aurora Serverless v2 PostgreSQL + pgvector (production, provisioned at Spec 2 via the RDS Data API), local pgvector via docker-compose (dev)
- **Frontend:** Vercel (plain HTML/CSS/JS, no framework)
- **Schedule:** EventBridge

## Model

Spec 0 proved invocation on: Amazon Nova Lite (`amazon.nova-lite-v1:0`), us-east-1, Aug 24 2026.

Production model selection is deferred to Spec 3 and will be decided by two numbers: verifier rejection rate on the same real packets, and measured cost per packet. Later specs must not assume a model provider that was never proven at invocation time.

## What it watches, and its honest limits

Porch Light watches the City of Ventura's public meeting agendas. It is built as
a **CivicEngage AgendaCenter adapter**, so the same code could serve other cities
on that platform — but the honest claim is CivicEngage AgendaCenter cities, not
"any CivicPlus site" and not "Ventura only." Reach is not the claim; the claim is
that the person who needs this most currently has nothing.

**How much warning you get: about five days to act, sometimes the same day.**
Measured across 135 real Ventura meetings, the median gap between an agenda
posting and its meeting is five days. But roughly one meeting in ten posts the
same day it happens — these are special and emergency meetings, exactly when a
resident most needs to know. A tool checked on a weekly rhythm cannot surface a
same-day meeting before it starts. We say this plainly rather than imply a
guarantee we cannot keep; closing that gap is future work, not a solved problem.

**Spanish.** Measured on one snapshot of the agenda index: 10 of 152 meetings
carried a Spanish agenda the city itself publishes — about one in fifteen overall,
and all of them City Council, where it is roughly one meeting in three. For those
meetings, we show the city's official Spanish document and the receipt points at it — we do not run our own translation over a
meeting the city already translated, because a receipt promises the linked
document says what we say it says, and our wording next to a link to a different
official document would break that promise. For the rest, the Spanish text is our
translation of the English source, verified against that source, and it is
labeled differently from a city-published edition so a reader always knows which
they are reading.

**Why we honor a robots.txt block we could ignore.** Ventura's agenda documents
are reachable on the city's own domain, which permits automated reading. The
city's separate Granicus video/agenda host tells all automated readers to stay
out, and we obey that even though robots.txt is a convention, not law. A product
whose entire claim is being a trustworthy reader of public records cannot quietly
override a public body's stated crawl preference: that is a hole in its own story,
and it is a findable one. Obeying it is the point, not a constraint we tolerate.

**A real civic-site behavior, and why our design absorbed it (§39).** When we
measured the city's agenda files, all 152 shared a single `Last-Modified`
timestamp — a server-side batch re-index had touched every file at once. Under
HTTP conditional GET, that makes **every document look changed**, so a
header-based system would re-download all 152 and, worse, could show 152 false
"new material" cards to someone who was watching. Porch Light does not do that: it
decides what changed by **content hash**, not by the header. On the run right
after a batch touch, all 152 files re-downloaded but every one hashed to its
existing id, so **no rows were written, no downstream work ran, and nobody's
briefing showed a false change.** We hit this by accident against the live site,
and the design gave the right answer with no user-visible effect. Conditional GET
is an optimization we use when it helps; content hash is the correctness mechanism
that holds when it does not.

**Where the model is, and deliberately is not.** The model has exactly three jobs:
rewrite staff language into plain English and Spanish, decide whether an item
matches a person's watchlist, and assemble the structure of a comment draft.
Everything else is deterministic code. In particular, the **hunter** — the part
that finds new agendas and classifies each document as an agenda, amendment,
supplemental, cancellation, or Spanish edition — uses no model at all. That
classification is a pure function of the document's URL and title, already
property-tested; a model there would be inventing judgment where there is none to
exercise, which is the exact failure our model-authority rules exist to prevent.
So of the system's work, **two of the three reasoning loops are genuine agents
(the extractor and the watcher); the hunter is deliberately not one.** We say this
plainly rather than dressing up deterministic code as an agent to look more
"agentic" — a reviewer reading the code would see through that, and it would
undercut the whole design principle of deterministic structure with AI only at the
edges.

## Setup

```bash
# Clone and start the local database
cp .env.example .env
docker compose up -d

# Install Python dependencies, including the test runner
uv sync --extra dev
```

Use `uv sync --extra dev`, not plain `uv sync`. Plain `uv sync` installs only
runtime dependencies and leaves the clone with no test runner, so `make test`
would fail on a fresh checkout. The `--extra dev` group brings in pytest and
hypothesis. (Verified from a clean clone into a temp directory: plain sync →
pytest absent; `--extra dev` → 57 tests pass.)

Before deploying to AgentCore, copy the deployment target template and fill in your own 12-digit AWS account ID (same pattern as `.env.example`):

```bash
cp deploy/spike_b/porchlightspike/agentcore/aws-targets.json.example \
   deploy/spike_b/porchlightspike/agentcore/aws-targets.json
# then edit aws-targets.json: replace <AWS_ACCOUNT_ID> with your account ID
```

The deployment state file (`agentcore/.cli/deployed-state.json`) is generated by `agentcore deploy` on first deploy; you do not create it by hand. Both files are gitignored because they carry account-specific resource identifiers.

Use `uv add <package>` to add a dependency, never `pip install` — pip installs work but do not update uv.lock, and the deploy build fails on the resulting drift.

## Deployment dependency governance

The deployed agent's dependency set is resolved by AgentCore server-side from `deploy/spike_b/porchlightspike/app/porchlight_spike/pyproject.toml`. That manifest pins exact versions (==). The `tests/test_deploy_pins.py` test asserts those pins match what `uv.lock` resolved, so a version bump in either place fails the default test suite until both agree.

## Local development

`docker compose up -d` brings up Postgres with pgvector. This is for local development only and is never the deployment path.

## Verifying a clean clone

```bash
make smoke
```

Runs live smoke tests against AWS. Makes real AWS calls and writes real CloudWatch log entries. Costs < $0.01 per run (one Converse call + one AgentCore invoke).

Tests skip (not fail) if credentials or endpoint are absent. A skip means "not proven on this machine." A failure means "the live system is broken or unreachable."

## Cost

The application spend ledger covers **model and API spend only**, with a ceiling
of $10/month (about 50x the measured steady-state spend of ~$0.20/month on Nova
Lite). Infrastructure is tracked separately (below) and is **not** bounded by that
$10 ledger ceiling. If you read "$10" as the monthly bill, this line is why that
is wrong.

Infrastructure cost, **estimated** (not yet measured):

- **Aurora Serverless v2 at min capacity 0 (development setting): ~$4–5/month.**
  Scale-to-zero needs an idle period before pausing, and the hourly ingestion run
  wakes the cluster every hour, so the real duty cycle is closer to ~10% than 0% —
  hence ~$4–5, not the ~$1 a naive "scales to zero" reading suggests. Verified
  rate: $0.12/ACU-hour in us-east-1. At the 0.5-ACU floor (raised at Spec 5 for the
  live watcher) it would be ~$44/month always-warm; we defer that.
- **Scheduler Lambda + EventBridge schedule: ~$0/month** (well within free tier).
- These are estimates. A Spec 3 task reads the actual number from Cost Explorer,
  filtered by our four tags, after a week of real runs, and replaces this estimate
  with the measurement.

## Wind-down

Porch Light reads a public body's servers on a schedule. The most important
wind-down obligation is therefore **stopping the crawler**, not saving money: a
forgotten pipeline hitting the City of Ventura every hour, indefinitely, is a
broken promise for a product whose entire claim is being a trustworthy reader of
public records. These teardown steps are written here before the resources are
created, in order.

1. **EventBridge schedule (stop this first — it touches someone else's server).**
   **This schedule is LIVE:** it invokes the hunter hourly, 24/7, and reads the
   City of Ventura's AgendaCenter each run (§39 — we run all hours for now; a
   narrower weekday window is set at Spec 3 once we have real posting-time data).
   **The command you want at 2am when something is wrong is DISABLE, not delete —**
   it stops the traffic instantly and is reversible:
   ```bash
   aws scheduler update-schedule --name porchlight-<env>-ingestion --state DISABLED \
     --schedule-expression "rate(1 hour)" --flexible-time-window "Mode=OFF" \
     --target "Arn=<hunter-lambda-arn>,RoleArn=<scheduler-invoke-role-arn>"
   # then, only when tearing down for good:
   aws scheduler delete-schedule --name porchlight-<env>-ingestion
   ```

2. **Hunter Lambda + its role (the deterministic ingestion job that fetches from
   Ventura).** The hunter is a plain Lambda invoked directly by the schedule (§38);
   once the schedule is gone nothing calls it, but delete it to leave nothing behind:
   ```bash
   aws lambda delete-function --function-name porchlight-<env>-hunter
   aws iam delete-role --role-name porchlight-<env>-hunter-role   # detach policies first
   aws iam delete-role --role-name porchlight-<env>-scheduler-invoke-role  # EventBridge→Lambda role
   ```

3. **Aurora Serverless v2 cluster (~$4–5/month at min capacity 0; ~$44/month if
   raised to 0.5 ACU at Spec 5).** After the schedule, Lambda, and runtime are
   stopped, delete the cluster and its associated resources:
   ```bash
   aws rds delete-db-cluster --db-cluster-identifier porchlight-<env> --skip-final-snapshot
   aws rds delete-db-instance --db-instance-identifier porchlight-<env>-instance --skip-final-snapshot
   aws secretsmanager delete-secret --secret-id porchlight-<env>-db --force-delete-without-recovery
   ```
   The city is the source of truth (§13): losing the database costs nothing to
   correctness, only a re-ingest. There is no backup-restore path to maintain.

Keep / park / take-down decision (per §13) is made deliberately, not in the moment;
the monthly costs above are the inputs.

## License

MIT
