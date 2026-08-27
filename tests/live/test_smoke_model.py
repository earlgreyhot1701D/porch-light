"""Live smoke test: Bedrock Converse responds in the expected region with the expected model.

This test makes a real AWS call. It is excluded from the default pytest run
and only runs via `make smoke` (pytest -m live).

Requirement 13: Live Smoke Tests.
Testing contract (.kiro/steering/testing.md): every spec that proves a live
capability leaves a re-runnable @pytest.mark.live test.
"""

from __future__ import annotations

import pytest
import boto3
from botocore.exceptions import NoCredentialsError

from porchlight.config import load_config

# Deliberate literals — tests are allowed to hardcode expected values.
# That is what an assertion is. Do not "fix" these by reading from config;
# doing so converts the test into a tautology that confirms our code agrees
# with itself rather than catching a misconfiguration.
# Exception to the "no hardcoded region outside config.py" rule (item 1, Aug 24).
EXPECTED_REGION = "us-east-1"
EXPECTED_MODEL_ID = "amazon.nova-lite-v1:0"


@pytest.mark.live
def test_bedrock_converse_responds() -> None:
    """One real Converse call. Asserts non-empty response, correct region, correct model.

    Skip ONLY on NoCredentialsError (no credentials configured at all).
    Fail on everything else: expired tokens, access denied, throttling, timeout.
    """
    # Resolve credentials early so we can skip cleanly if absent.
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials is None:
            pytest.skip("No AWS credentials configured (credential chain empty)")
        # Force resolution to catch NoCredentialsError before the call.
        credentials.get_frozen_credentials()
    except NoCredentialsError:
        pytest.skip("No AWS credentials configured (NoCredentialsError)")

    # Load config to verify it matches our expected values.
    config = load_config(component="spike")

    # Assert config matches expected (catches config drift).
    assert config.aws_region == EXPECTED_REGION, (
        f"Config region '{config.aws_region}' does not match expected '{EXPECTED_REGION}'"
    )

    # Create client and make the real call.
    client = boto3.client("bedrock-runtime", region_name=config.aws_region)

    # Assert the client resolved to the expected region (public attribute).
    assert client.meta.region_name == EXPECTED_REGION, (
        f"Client region '{client.meta.region_name}' does not match expected '{EXPECTED_REGION}'"
    )

    # Make the real Converse call. Do NOT wrap in broad try/except.
    response = client.converse(
        modelId=config.model_id,
        messages=[
            {
                "role": "user",
                "content": [{"text": "Say hello in exactly three words."}],
            }
        ],
    )

    # Assert on values that could only originate from the remote system.
    output_text = response["output"]["message"]["content"][0]["text"]
    assert output_text, "Model returned empty response text"
    assert len(output_text) > 0, "Response text has zero length"

    # Assert model id matches expected.
    # Nova Lite doesn't echo model_id in the response body, so we verify
    # we called the right model by checking our config against the literal.
    assert config.model_id == EXPECTED_MODEL_ID, (
        f"Config model_id '{config.model_id}' does not match expected '{EXPECTED_MODEL_ID}'"
    )
