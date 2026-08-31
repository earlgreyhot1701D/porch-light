"""Live smoke test: the deployed extractor's tool-allowlist hook still blocks (R5 condition 2).

testing.md obligation 1: a live capability proven once and never re-checked is not
proven. R5 proved, against the deployed AgentCore runtime, that a non-allowlisted
tool the model calls is blocked by the Strands hook and logged as a NEVER-trip. This
test re-proves it on demand via `make smoke`, so if the allowlist ever SILENTLY
stops firing (a strands upgrade renames the hook event again, the hook fails to
register, etc.), this test fails loudly.

Testing principle (recorded in the decisions doc): TEST THE CONTROL, NOT THE THING
THE CONTROL SITS BEHIND. The probe uses a BENIGN, plainly-safe tool that simply is
not on the allowlist. A malicious-intent tool would be refused by the
model's own safety before the hook ran — a pass there would measure the model's
alignment, not our allowlist. The allowlist blocks by NAME, so a benign
non-allowlisted tool is the valid test.

Real AWS calls (AgentCore invoke + CloudWatch Logs). Excluded from the default run;
runs via `make smoke`. Skips only when the extractor runtime env var is unset.
"""

from __future__ import annotations

import json
import os
import time

import boto3
import pytest
from botocore.exceptions import NoCredentialsError

# The DEPLOYED extractor runtime ARN (distinct from the spike's). Set from
# deployed-state.json / the deploy outputs.
EXTRACTOR_ARN_VAR = "AGENTCORE_EXTRACTOR_RUNTIME_ARN"
REGION_VAR = "AGENTCORE_REGION"
LOG_GROUP_VAR = "AGENTCORE_EXTRACTOR_LOG_GROUP"

# The NEVER-trip our hook emits when it blocks a non-allowlisted tool.
NEVER_TRIP_EVENT = "never_trip_tool_blocked"


def _config() -> tuple[str, str, str]:
    arn = os.environ.get(EXTRACTOR_ARN_VAR)
    if not arn:
        pytest.skip(
            f"{EXTRACTOR_ARN_VAR} not set: no deployed extractor runtime to test. "
            f"Set it to the extractor runtime ARN to run this smoke test."
        )
    region = os.environ.get(REGION_VAR, "us-east-1")
    runtime_id = arn.rsplit("/", 1)[-1] if "/" in arn else arn
    log_group = os.environ.get(
        LOG_GROUP_VAR, f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"
    )
    return arn, region, log_group


def _ensure_credentials() -> None:
    try:
        creds = boto3.Session().get_credentials()
        if creds is None:
            pytest.skip("No AWS credentials configured (credential chain empty)")
        creds.get_frozen_credentials()
    except NoCredentialsError:
        pytest.skip("No AWS credentials configured (NoCredentialsError)")


@pytest.mark.live
def test_extractor_allowlist_still_blocks_a_non_allowlisted_tool() -> None:
    """Invoke the deployed extractor with the containment probe; assert the hook
    logged a NEVER-trip for the benign, non-allowlisted tool. If the allowlist
    silently stops firing, this fails."""
    arn, region, log_group = _config()
    _ensure_credentials()

    client = boto3.client("bedrock-agentcore", region_name=region)
    client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        contentType="application/json",
        accept="application/json",
        # _containment_probe plants a benign non-allowlisted tool and asks the model
        # to call it (see agents/extractor/entrypoint.py). The hook must block it.
        payload=json.dumps({
            "pages": ["Item 1."],
            "document_id": "smoke-containment-probe",
            "_containment_probe": True,
        }).encode("utf-8"),
    )

    time.sleep(10)  # CloudWatch log ingestion

    logs_client = boto3.client("logs", region_name=region)
    now_ms = int(time.time() * 1000)
    resp = logs_client.filter_log_events(
        logGroupName=log_group,
        startTime=now_ms - 120_000,  # last 2 minutes
        endTime=now_ms,
        limit=100,
    )
    events = resp.get("events", [])
    assert events, f"No CloudWatch events in {log_group} in the last 2 minutes."

    # Find our structured NEVER-trip: {event: never_trip_tool_blocked,
    # boundary: tool_allowlist, component: extractor, level: warning}
    never_trips = []
    for e in events:
        try:
            parsed = json.loads(e.get("message", ""))
        except (json.JSONDecodeError, TypeError):
            continue
        if parsed.get("event") == NEVER_TRIP_EVENT and parsed.get("boundary") == "tool_allowlist":
            never_trips.append(parsed)

    assert never_trips, (
        "The extractor allowlist hook did NOT log a NEVER-trip for a non-allowlisted "
        "tool. Either the hook stopped firing (silent containment failure) or the "
        "probe path changed. This is the exact regression this test exists to catch."
    )
    trip = never_trips[-1]
    assert trip.get("component") == "extractor"
    assert trip.get("level") == "warning"
    assert trip.get("tool_name"), "NEVER-trip missing the blocked tool_name"
