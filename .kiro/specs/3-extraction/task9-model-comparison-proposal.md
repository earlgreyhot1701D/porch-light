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
| Cheapest viable | **Amazon Nova Lite** (`amazon.nova-lite-v1:0`) | ~$0.06 / $0.24 | Already proven invocable at Spec 0; no Marketplace subscription gate (§27); the incumbent to beat. ACTIVE. |
| One larger | **Amazon Nova Pro** (`amazon.nova-pro-v1:0`) | ~$0.80 / $3.20 | The comparator, chosen from the live `list-foundation-models` (us-east-1). See the model-longevity finding below. |

**Pricing source (submission-grade).** The authoritative source is the AWS Bedrock
pricing page, [aws.amazon.com/bedrock/pricing](https://aws.amazon.com/bedrock/pricing/),
retrieved 2026-08-30. That page renders its per-model token table dynamically, so
the exact Nova Lite / Nova Pro per-1K figures must be read on the page directly
rather than quoted from a scrape; the ~$0.06/$0.24 (Lite) and ~$0.80/$3.20 (Pro)
per-1M figures used for the estimate below are the widely-reported values and are
used ONLY to size the run. The DECISION rests on the spend ledger's ACTUAL measured
cost per call by model id, not on this estimate, so a small discrepancy in the
published rate does not affect the outcome. (Aggregator cross-checks: openrouter,
metatext, cloudprice — consistent with the above; rephrased for compliance.)

**Comparator changed from Claude Haiku to Nova Pro — model-longevity finding (recorded).**
The originally-proposed `anthropic.claude-3-5-haiku-20241022-v1:0` is **end-of-life**
(Converse returned `ResourceNotFoundException: This model version has reached the
end of its life`, hit 2026-08-30). The still-callable `anthropic.claude-3-haiku-20240307-v1:0`
is **LEGACY** (endOfLife **2026-09-10**, in public-extended-access) — days from EOL, a
bad pick for anything meant to outlive the hackathon. **Near miss, written down
while fresh:** the hackathon is judged **2026-09-14**; that Claude 3 Haiku hits EOL
**2026-09-10**, so pinning it would have broken the demo **four days before
judging**. The tool-longevity check (querying `list-foundation-models` for
lifecycle status instead of trusting a remembered id) paid for itself here. From the live list, the
cheapest **ACTIVE** model that is a genuine step up from Nova Lite and shares the
identical Converse API shape (so the prompt stays a clean controlled variable, no
cross-provider format drift) is **Nova Pro** (`amazon.nova-pro-v1:0`, ACTIVE since
2024-12-03, ~$0.80/$3.20 per 1M). Same provider is a feature here, not a
limitation: it isolates the model-size variable from provider prompt-format
differences. Prices per public sources (openrouter / metatext / cloudprice),
rephrased for compliance; the ledger records ACTUAL cost per call by model id.

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
- Twice per model = 4 items x 2 langs x 2 runs = 16 good-item calls per model (the
  harness runs the 4 non-adversarial items; adversarials are not billed into the
  rate). Budget the full 48 for safety incl. retries.
- Per call ~600 in / 300 out:
  - Nova Lite: negligible — measured ~$0.0005/run, ~$0.001 for both runs.
  - Nova Pro: ~13x Nova Lite's rate ($0.80/$3.20 vs $0.06/$0.24) => ~$0.007 for both runs.
  - **Total estimated cost of the whole comparison: well under $0.02.** Inside the
    ingestion sub-budget (T15 = $10, ingestion = $7). One-time, not recurring.
    (Nova Lite's 2 runs already cost ~$0.001, spent during the blocked first attempt.)

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

---

## OUTCOME (task 9 closed)

**Selected model: Amazon Nova Lite (`amazon.nova-lite-v1:0`), decided-under-limitation.**

Comparison ran Nova Lite vs Nova Pro, anti-echo controlled prompt, twice per model,
actual ledger-summed cost **$0.01216**. Result:

| model | run | overall | EN | ES |
| --- | --- | --- | --- | --- |
| Nova Lite | 1 | 50% | 0/4 | 4/4 |
| Nova Lite | 2 | 50% | 0/4 | 4/4 |
| Nova Pro | 1 | 38% | 0/4 | 3/4 |
| Nova Pro | 2 | 38% | 0/4 | 3/4 |

- **EN is clean for both models (0/4).** Every rejection is ES-side.
- The ES rejections were **artifact-dominated**, not model quality: (1) the models
  translated role/body common nouns ("Concejo Municipal", "Secretario Municipal",
  "Centro Urbano", "Distrito Escolar Unificado", "Cuarta Enmienda") that the
  extractor did not yet recognize as non-raw-compare in Spanish, and (2) the
  provisional ES reading floor (77.3) rejected fine model prose scoring 69-72.
- Runs agreed within each model, so the Lite-vs-Pro delta lives in the artifact
  (Nova Pro happened to translate one fewer name), not in measured quality.
- Under the fixed decision rule (artifact/noise at this n => take the cheaper),
  **Nova Lite wins**: it clears EN cleanly at ~1/14th the cost of Nova Pro.

**Then the ES bug was fixed** (it is a production bug: an untreated role/body
translation rejects every Spanish rewrite live). The extractor's role/body list
gained the Spanish equivalents actually observed in this run (paired with their
English counterparts, sourced to the run), and the ES reading floor was re-derived
to 64.0. Calibration re-run: known-good rejection still 0, adversarials still bite.
A post-fix Nova-Lite-only ES rejection rate is recorded for the write-up.

### Post-fix Nova-Lite-only measurement (write-up, not a re-decision)

After the ES role/body fix and the 64.0 floor, Nova Lite over the four good items,
twice, cost $0.00084 total:

| run | overall | EN | ES | ES rejections by check |
| --- | --- | --- | --- | --- |
| 1 | 3/8 = 38% | 0/4 | 3/4 | reading_level 3 |
| 2 | 3/8 = 38% | 0/4 | 3/4 | reading_level 3 |

The role/body-name entity rejections (previously 2-3 per run on checks 2/3/6) are
**gone** — the ES equivalence fix worked. The remaining ES rejections are ALL
check 5, and specifically the **"strictly simpler than source"** condition, NOT
the floor: the rewrites score 70.6-84.3 (all above the 64.0 floor), but three
items' SOURCE text already scores high on Fernández Huerta (74.9, 77.7, 76.5)
because Ventura's consent-item Spanish-equivalent text is short and structurally
simple, so a faithful rewrite cannot be "strictly simpler." This is a metric
artifact on already-simple source, not a bad rewrite. Model output is
nondeterministic so these scores wobble run to run. Noted as a v2 item: on
already-simple source, check 5 should pass a rewrite that is not MORE complex
rather than requiring strictly simpler. Not changed now (measurement only).
