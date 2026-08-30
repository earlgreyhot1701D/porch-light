# Task 9 — model comparison PROPOSAL (no calls until approved)

Status: **PROPOSE ONLY.** No paid model call runs until Shara approves this plan.
Gate met: verifier calibrated on 0a (known-good rejection = 0, both adversarials
bite). 0b deferred (see tasks.md 0b). This comparison runs over the ten known-good
0a rewrites' SOURCES, re-deriving each model's rewrites and scoring them with the
already-calibrated verifier.

## 1. Which models, and why

Exactly two, per the "cheapest viable vs one larger, not a field of four" rule:

| Role | Model | On-demand price (per 1M tok, in/out) | Why |
| --- | --- | --- | --- |
| Cheapest viable | **Amazon Nova Lite** (`amazon.nova-lite-v1:0`) | ~$0.06 / $0.24 | Already proven invocable at Spec 0; no Marketplace subscription gate (§27); the incumbent to beat. |
| One larger | **Claude Haiku** (current 3.x, `anthropic.claude-3-5-haiku-*`) | ~$0.25 / $1.25 | Cheapest Claude tier — one clear step up in capability, still cheap. NOT a Sonnet: the question is "is the cheap model good enough," and Haiku is the honest one-step comparator. |

Prices are approximate current on-demand Bedrock rates (sources below); the ledger
records ACTUAL cost per call by model id (already built, R9.1), so the decision
rests on measured cost, not this estimate.

- Model id is **read from config, never hardcoded** (§27); each model's id is in
  every structured log event so the run is attributable.
- **No silent fallback** between them (never.md #7): each is invoked deliberately;
  a failure is recorded as a failure, not swapped.

## 2. Exact call count and estimated cost

- Chain per item = 2 model calls (EN rewrite, then ES translate-of-verified-EN).
- 6 items x 2 calls = **12 calls per model**; x 2 models = **24 calls** baseline.
- Retry budget: check-fail → one retry with reason (existing policy). Worst case
  doubles to **48 calls**. Plan for 48, expect ~24-30.
- Token estimate per call: source page-range ~300-500 input tokens, rewrite output
  ~150-250 tokens. Generously 600 in / 300 out per call.
- 48 calls x (600 in + 300 out):
  - Nova Lite: 28.8k in x $0.06/1M + 14.4k out x $0.24/1M = **~$0.005**
  - Claude Haiku: 28.8k in x $0.25/1M + 14.4k out x $1.25/1M = **~$0.025**
  - **Total estimated cost of the whole comparison: under $0.05.** Well inside the
    ingestion sub-budget (T15 = $10, ingestion = $7). One-time, not recurring.

## 3. What is measured

Over the ten known-good 0a items, for EACH model:

- **Verifier rejection rate** — the headline number (R5). Reported three ways:
  - per model (overall % of rewrites rejected),
  - per check (which of the six checks rejects, and how often),
  - per language (EN vs ES rejection rate — the ES chain is the harder half).
- **Cost per agenda** — from the spend ledger by model id (actual, not estimated).
- **Attempts** — how often each model needed the one retry (a proxy for reliability).
- Adversarial items are EXCLUDED from the rejection-rate denominator (they must be
  rejected by construction); they are run only to confirm both models' rewrites of
  the CORRECT-language side still pass, i.e. the model did not accidentally
  reproduce the poison.

Recorded to a comparison table + a builder.aws.com-style note (§11), model id in
every log line.

## 4. The decision rule (written before the run, so the result cannot move it)

- **Pick Nova Lite (the cheaper) if** its known-good rejection rate is 0 (or ties
  Haiku) across both languages. A model that clears the verifier on every good
  rewrite is good enough; paying 5x more for the same measured quality is not
  justified for a free civic tool.
- **Pick Haiku only if** it has a materially lower rejection rate on the good
  rewrites AND the failures are a real quality gap (e.g. Nova Lite drops entities
  or fails the ES chain on a class of item), not random noise on 1-2 items.
- **If the result is ambiguous** (both non-zero, or failures cluster on a class of
  item), that is the 0b trigger: add golden items covering that class, then re-run
  — do NOT pick on a six-item tie.
- Whichever wins, the choice + both numbers are written down (README + §27 record).
  The losing model is not wired in as a fallback (never.md #7).

## 5. What running it will and will not touch

- Adds `rewrite/chain.py` + `rewrite/model.py` (the chain; Strands-vs-Converse
  decided here on evidence, recorded — not assumed) and a comparison harness under
  `tests/golden/`. Model id from config.
- Does NOT change the verifier, the normalizer, or `source.text`.
- Uses the existing `ledger.record_model_spend` (run_id + model id) for cost.

---

Sources (approximate current Bedrock on-demand pricing; content rephrased for
licensing compliance):
- [markaicode — AWS Bedrock latency benchmark 2026](https://markaicode.com/benchmarks/aws-bedrock-production-benchmark-latency/) (Nova Lite $0.06/$0.24 per 1M)
- [markaicode — AWS Bedrock pricing](https://markaicode.com/pricing/aws-bedrock-pricing/) (Claude Haiku ~$0.00025 per 1K input)
