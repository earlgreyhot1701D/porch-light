"""Rewrite model invocation — direct Bedrock Converse, temp ~0, no tools (§21b, §27).

Decision recorded (design left it open): the rewrite goes through **direct Bedrock
Converse**, not the Strands agent machinery. Reason: the rewrite has no tools and
no loop — it is a single structured generation — so the agent runtime would be
overhead with no benefit (§model-authority: a rewrite is not an agent action). The
extractor and watcher are agents; the rewrite is a call.

Rules enforced here:
  - **Model id is read from config, never hardcoded** (§27). Passed in explicitly
    so a comparison run can drive two models through the identical path.
  - **No silent fallback** (never.md #7): a failed call raises; the caller records
    the failure, it is never swapped for another provider.
  - Temperature ~0 for determinism-leaning output; the model translates and
    simplifies, it does not invent (never.md #1 is enforced downstream by the
    verifier, not trusted here).
  - Cost is recorded per call by run_id + model id via the spend ledger (R9.1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import boto3

# Approximate on-demand Bedrock prices (USD per token), used ONLY to estimate cost
# when a Converse response omits usage; the ledger prefers real token counts when
# present. Values are per the task-9 proposal's sourced rates.
_PRICE_PER_TOKEN = {
    # model_id substring -> (input_price, output_price) per 1 token.
    # Order matters: "nova-pro" before "nova" so the longer key wins.
    "nova-pro": (0.80 / 1_000_000, 3.20 / 1_000_000),
    "nova-lite": (0.06 / 1_000_000, 0.24 / 1_000_000),
    "haiku": (0.25 / 1_000_000, 1.25 / 1_000_000),
}


@dataclass(frozen=True)
class ModelResponse:
    """One Converse result: the text plus token usage and computed cost."""

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model_id: str


def _price_for(model_id: str) -> tuple[float, float]:
    for key, price in _PRICE_PER_TOKEN.items():
        if key in model_id:
            return price
    return (0.0, 0.0)  # unknown model: cost recorded as 0, flagged by ledger review


def invoke(
    model_id: str,
    system_prompt: str,
    user_text: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 512,
    client=None,
) -> ModelResponse:
    """Invoke a model via Bedrock Converse. Model id is explicit (config-driven, §27).

    Raises on failure — the caller records it; there is no silent fallback to
    another model (never.md #7).
    """
    bedrock = client or boto3.client("bedrock-runtime")
    resp = bedrock.converse(
        modelId=model_id,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"temperature": temperature, "maxTokens": max_tokens},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    usage = resp.get("usage", {})
    in_tok = int(usage.get("inputTokens", 0))
    out_tok = int(usage.get("outputTokens", 0))
    in_price, out_price = _price_for(model_id)
    cost = in_tok * in_price + out_tok * out_price
    return ModelResponse(
        text=text,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
        model_id=model_id,
    )
