"""Spike: Prove Bedrock model invocation works.

Calls Converse with Nova Lite in the target region.
Logs result using the production logging module.
Exit 0 on success, non-zero on failure.

This is THROWAWAY code. It proves invocation works and then stops mattering.
"""

from __future__ import annotations

import sys

import boto3

from porchlight.config import load_config
from porchlight.log import bind_context, generate_run_id, get_logger


def main() -> int:
    config = load_config(component="spike")
    run_id = generate_run_id()
    bind_context(component=config.component, run_id=run_id, model_id=config.model_id)
    logger = get_logger(__name__)

    logger.info("prove_model_start", region=config.aws_region, model_id=config.model_id)

    try:
        client = boto3.client("bedrock-runtime", region_name=config.aws_region)
        response = client.converse(
            modelId=config.model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Say hello in exactly three words."}],
                }
            ],
        )
        output_text = response["output"]["message"]["content"][0]["text"]
        logger.info(
            "prove_model_success",
            response_preview=output_text[:200],
            stop_reason=response.get("stopReason", "unknown"),
        )
        print(f"PASS: Model responded: {output_text}")
        return 0

    except Exception as e:
        logger.error("prove_model_failure", error=str(e), error_type=type(e).__name__)
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
