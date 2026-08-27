"""Live smoke test: AgentCore runtime responds and logs with our structured schema.

This test makes real AWS calls (AgentCore invoke + CloudWatch Logs).
It is excluded from the default pytest run and only runs via `make smoke`.

Requirement 13: Live Smoke Tests.
Testing contract: every spec that proves a live capability leaves a
re-runnable @pytest.mark.live test.

Skip ONLY when the runtime env var is unset (no runtime to test).
Fail on every error from a runtime that exists.
"""

from __future__ import annotations

import json
import os
import re
import time

import boto3
import pytest
from botocore.exceptions import NoCredentialsError

# --- Configuration (env vars) ---
# AGENTCORE_RUNTIME_ARN: the deployed runtime ARN (from deployed-state.json)
# AGENTCORE_REGION: region where the runtime is deployed
# AGENTCORE_LOG_GROUP: the CloudWatch log group for the runtime

RUNTIME_ARN_VAR = "AGENTCORE_RUNTIME_ARN"
REGION_VAR = "AGENTCORE_REGION"
LOG_GROUP_VAR = "AGENTCORE_LOG_GROUP"

# Deliberate expected values for assertions. Tests are allowed to hardcode
# expected values: that is what an assertion is.
EXPECTED_GREETING_FRAGMENT = "Hello"
EXPECTED_TIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _get_runtime_config() -> tuple[str, str, str]:
    """Return (runtime_arn, region, log_group) or skip if unset."""
    runtime_arn = os.environ.get(RUNTIME_ARN_VAR)
    if not runtime_arn:
        pytest.skip(
            f"{RUNTIME_ARN_VAR} not set: no AgentCore runtime to test. "
            f"Set it to run this smoke test."
        )

    region = os.environ.get(REGION_VAR, "us-east-1")
    # Default log group derives from the runtime ID in the ARN
    runtime_id = runtime_arn.rsplit("/", 1)[-1] if "/" in runtime_arn else runtime_arn
    log_group = os.environ.get(
        LOG_GROUP_VAR,
        f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT",
    )
    return runtime_arn, region, log_group


def _ensure_credentials() -> None:
    """Skip cleanly if no AWS credentials are available."""
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials is None:
            pytest.skip("No AWS credentials configured (credential chain empty)")
        credentials.get_frozen_credentials()
    except NoCredentialsError:
        pytest.skip("No AWS credentials configured (NoCredentialsError)")


def _invoke_runtime(runtime_arn: str, region: str, prompt: str) -> str:
    """Invoke AgentCore runtime and return the reassembled response text.

    The response is an SSE stream of JSON events. We extract text deltas
    from contentBlockDelta events and concatenate them.
    """
    client = boto3.client("bedrock-agentcore", region_name=region)

    response = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        contentType="application/json",
        accept="application/json",
        payload=json.dumps({"prompt": prompt}).encode("utf-8"),
    )

    # Read the streaming body (SSE format: "data: {json}\n\n")
    raw = response["response"].read().decode("utf-8")

    # Parse SSE events and reassemble text from contentBlockDelta events
    text_parts: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            event_data = json.loads(line[6:])  # strip "data: " prefix
            event = event_data.get("event", {})
            delta = event.get("contentBlockDelta", {}).get("delta", {})
            if "text" in delta:
                text_parts.append(delta["text"])
        except (json.JSONDecodeError, TypeError):
            continue

    return "".join(text_parts)


@pytest.mark.live
def test_agentcore_invoke_responds_with_greeting_and_time() -> None:
    """Invoke the deployed AgentCore runtime and assert it returns a greeting and UTC time.

    Fail on every error from a runtime that exists.
    """
    runtime_arn, region, _log_group = _get_runtime_config()
    _ensure_credentials()

    body = _invoke_runtime(
        runtime_arn, region, "Say hello to Porch Light and tell me the time."
    )

    assert body, "AgentCore runtime returned empty response"
    assert EXPECTED_GREETING_FRAGMENT in body, (
        f"Response does not contain expected greeting '{EXPECTED_GREETING_FRAGMENT}'.\n"
        f"Got: {body[:300]}"
    )
    assert EXPECTED_TIME_PATTERN.search(body), (
        f"Response does not contain a UTC timestamp.\n"
        f"Got: {body[:300]}"
    )


@pytest.mark.live
def test_agentcore_cloudwatch_carries_our_schema() -> None:
    """After an invoke, CloudWatch must contain a record with our component and run_id fields.

    This proves the structlog processor chain (including redaction) is running
    in the deployed AgentCore runtime, not just locally.
    """
    runtime_arn, region, log_group = _get_runtime_config()
    _ensure_credentials()

    # Invoke to generate a fresh log entry
    _invoke_runtime(
        runtime_arn, region, "Say hello to Porch Light and tell me the time."
    )

    # Wait for CloudWatch log ingestion (typically 2-5 seconds)
    time.sleep(8)

    # Query CloudWatch for recent events
    logs_client = boto3.client("logs", region_name=region)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 60_000  # last 60 seconds

    events_response = logs_client.filter_log_events(
        logGroupName=log_group,
        startTime=start_ms,
        endTime=now_ms,
        limit=20,
    )

    events = events_response.get("events", [])
    assert events, (
        f"No CloudWatch events found in {log_group} within the last 60 seconds. "
        f"The runtime may not be logging, or log ingestion is delayed."
    )

    # Find at least one event with our schema fields: component, run_id
    our_events = []
    for event in events:
        message = event.get("message", "")
        try:
            parsed = json.loads(message)
            if "component" in parsed and "run_id" in parsed:
                our_events.append(parsed)
        except (json.JSONDecodeError, TypeError):
            continue

    assert our_events, (
        f"Found {len(events)} CloudWatch events but none carry our schema "
        f"(component + run_id). The structlog processor chain may not be "
        f"running in the deployed runtime."
    )

    # Verify the schema fields on the first match
    record = our_events[0]
    assert record["component"] == "spike", (
        f"Expected component='spike', got '{record.get('component')}'"
    )
    assert record["run_id"].startswith("run_"), (
        f"run_id does not match expected format: '{record.get('run_id')}'"
    )
    assert "level" in record, "Record missing 'level' field"
    assert "timestamp" in record, "Record missing 'timestamp' field"
