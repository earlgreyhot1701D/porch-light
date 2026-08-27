"""Spike B — trivial Strands agent deployed to AgentCore.

THROWAWAY code. Proves the deployment path works, then stops mattering.

Pass criteria (Requirement 11 — written before code):
- agentcore deploy succeeds to us-east-1
- Invoke endpoint returns non-error response within 30 seconds
- CloudWatch log contains structured JSON with valid run_id and component "spike"
- All four cost tags visible on created resources
- Verify endpoint requires SigV4 (unsigned request gets 401/403)

Additional pass criterion (§31 finding, added post-spike):
- CloudWatch record carries OUR JSON schema: component, run_id, level, message
- Truncation marker appears for oversized extra fields
- Redaction marker appears for document-content keys

Teardown command (criterion d — exists before resources do):
  agentcore deploy --target default --yes   (to deploy)
  # To tear down: delete the CDK stack via:
  #   cd deploy/spike_b/porchlightspike/agentcore && npx cdk destroy --all --force
  # Also clean up CDKToolkit bootstrap stack if no longer needed:
  #   aws cloudformation delete-stack --stack-name CDKToolkit --region us-east-1

Findings to record for later specs:
- §30d: PUBLIC networkMode allows outbound egress over public internet.
  §19 requires extractor to have no network egress. VPC networkMode with
  no egress route, or the claim must be downgraded. Spec 3 decision.
- Partial stream failure: a stream that dies partway through leaves the user
  a partial answer, which looks complete. Tenth §16b failure state, Spec 5.
"""

import os
from typing import Any

from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from porchlight.log import bind_context, generate_run_id, get_logger

app = BedrockAgentCoreApp()


# ---- Tools (same as Spike A) ----

@tool
def hello_tool(name: str) -> str:
    """Returns a greeting for the given name."""
    return f"Hello, {name}!"


from datetime import datetime, timezone


@tool
def time_tool() -> str:
    """Returns the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ---- Agent setup ----

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")


@app.entrypoint
async def invoke(payload: dict[str, Any], context: Any):
    """Handle an invocation from AgentCore."""
    run_id = generate_run_id()

    # Initialize OUR structured logging: binds component + run_id to contextvars,
    # configures structlog processor chain including the redaction processor,
    # and routes all stdlib logging through our JSON renderer.
    bind_context(component="spike", run_id=run_id, model_id=MODEL_ID)
    log = get_logger("porchlight.spike")

    # --- Event 1: Normal structured event (proves our schema) ---
    log.info("spike_b_start", prompt_length=len(payload.get("prompt", "")))

    # --- Event 2: Oversized extra field (proves truncation processor) ---
    oversized_value = "x" * 1000  # 1000 chars > 512 cap
    log.info("spike_b_truncation_test", big_field=oversized_value)

    # --- Event 3: Document-content key (proves redaction processor) ---
    log.info(
        "spike_b_redaction_test",
        document_content_raw="This should never appear in CloudWatch",
    )

    prompt = payload.get("prompt", "Say hello to Porch Light and tell me the time.")

    agent = Agent(model=MODEL_ID, tools=[hello_tool, time_tool])

    async for event in agent.stream_async(prompt):
        if not isinstance(event, dict) or "event" not in event:
            continue
        yield event

    log.info("spike_b_complete")


if __name__ == "__main__":
    app.run()
