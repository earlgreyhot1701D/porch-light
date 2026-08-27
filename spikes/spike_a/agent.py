"""Spike A — trivial Strands agent with two tools, running locally.

Pass criteria (Requirement 11 — written before code):
- Agent calls both tools (visible in response)
- At least one structured JSON log line emitted with valid run_id
- Exit 0 on success, non-zero on failure

THROWAWAY code. Proves the SDK works locally, then stops mattering.
"""

from __future__ import annotations

import sys

from strands import Agent

from porchlight.config import load_config
from porchlight.log import bind_context, generate_run_id, get_logger
from spikes.spike_a.tools import hello_tool, time_tool


def main() -> int:
    config = load_config(component="spike")
    run_id = generate_run_id()
    bind_context(component=config.component, run_id=run_id, model_id=config.model_id)
    logger = get_logger(__name__)

    logger.info("spike_a_start")

    try:
        agent = Agent(model=config.model_id, tools=[hello_tool, time_tool])
        result = agent("Say hello to Porch Light and tell me the current time.")

        response_text = str(result)
        logger.info("spike_a_complete", result_preview=response_text[:200])
        print(f"PASS: Agent responded: {response_text[:300]}")
        return 0

    except Exception as e:
        logger.error("spike_a_failure", error=str(e), error_type=type(e).__name__)
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
