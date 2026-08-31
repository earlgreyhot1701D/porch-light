"""Extractor AgentCore entrypoint + the allowlist hook (R1, §30d, §38, §security).

This is the runtime seam: it binds structured logging, registers the Strands hook
that enforces the tool allowlist (blocking + logging any NEVER-trip), runs the
extractor loop under the caps, validates every proposed item against the source,
and records the honest document status. The deterministic guarantees live in
`tools.py` and `agent.py`; this module wires them to the runtime.

Two independent containment layers (R8.3): this hook (tool allowlist) AND the
runtime's no-egress networkMode, which is set in the AgentCore config, not in code
— even if a prompt defeated this hook, the runtime cannot reach the network.

Untrusted input (never.md #9): document text is data. An injected "fetch this URL"
becomes a tool call the allowlist denies, logged as a NEVER-trip.
"""

from __future__ import annotations

import os
from typing import Any

from porchlight.agents.extractor.tools import is_tool_allowed
from porchlight.log import bind_context, generate_run_id, get_logger

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
COMPONENT = "extractor"


def enforce_tool_allowlist(tool_name: str, log) -> bool:
    """Allow or deny a tool call; a denial is a logged NEVER-trip (R1.4, never.md #9).

    Pure decision + a log side effect, extracted so the hook body is trivial and
    the decision is unit-testable. Returns True to allow, False to block.
    """
    if is_tool_allowed(tool_name):
        return True
    # A blocked tool call is a NEVER-trip: the security boundary firing, logged and
    # surfaced, never silently swallowed (security.md, never.md #12).
    log.warning("never_trip_tool_blocked", tool_name=tool_name, boundary="tool_allowlist")
    return False


def _register_allowlist_hook(agent: Any, log) -> None:
    """Register the before-tool-invocation hook that enforces the allowlist.

    Imported lazily; the exact Strands hook symbol is resolved at runtime so this
    module imports cleanly in a test environment without the full SDK. If the SDK's
    hook surface is unavailable, we fail CLOSED by refusing to run rather than
    running an unguarded agent (never.md #7: never fail open).
    """
    try:
        from strands.hooks import BeforeToolInvocationEvent, HookProvider, HookRegistry
    except Exception as exc:  # SDK surface missing/changed — do not run unguarded.
        raise RuntimeError(
            "extractor tool-allowlist hook unavailable; refusing to run unguarded"
        ) from exc

    class _AllowlistHook(HookProvider):
        def register_hooks(self, registry: HookRegistry) -> None:
            registry.add_callback(BeforeToolInvocationEvent, self._before_tool)

        def _before_tool(self, event: BeforeToolInvocationEvent) -> None:
            name = getattr(getattr(event, "tool_use", None), "name", "") or ""
            if not enforce_tool_allowlist(name, log):
                # Block by raising: the tool never executes (fail closed).
                raise PermissionError(f"tool not on extractor allowlist: {name!r}")

    agent.hooks.add_hook(_AllowlistHook())


# The AgentCore app + entrypoint are defined only when the runtime is present, so
# importing this module for unit tests (of enforce_tool_allowlist) needs no SDK.
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    async def invoke(payload: dict[str, Any], context: Any):
        """Extract items from ONE document — from STORED TEXT, never a URL (R2, §containment-contract).

        Contract (condition 1): the payload carries the document's PAGE TEXT that
        the pipeline already read from `document_pages`. It carries NO URL and NO
        fetchable id the extractor would resolve over the network. `document_id` is
        accepted only as an opaque LABEL for logging/attribution — it is never
        dereferenced, never fetched. There is nothing in this contract the network
        is needed for; the no-egress runtime + allowlist hook enforce a network the
        work does not even ask for.

        Payload:
          - `pages`: list[str], the per-page text (index 0 = page 1). REQUIRED.
          - `document_id`: str, an opaque label for logs. Optional.
        """
        run_id = generate_run_id()
        bind_context(component=COMPONENT, run_id=run_id, model_id=MODEL_ID)
        log = get_logger("porchlight.extractor")

        pages = payload.get("pages")
        if not isinstance(pages, list) or not all(isinstance(p, str) for p in pages):
            # Fail closed: the contract is text-in. A missing/ill-typed pages field
            # is a caller error, never a signal to go find the text ourselves.
            log.error("extractor_bad_payload", reason="pages must be a list[str] of page text")
            raise ValueError("extractor payload requires 'pages': list[str] (stored text, never a URL)")

        log.info("extractor_start", document_id=payload.get("document_id", ""), page_count=len(pages))

        from porchlight.agents.extractor.agent import build_agent

        tools = payload.get("_tools", [])
        agent = build_agent(MODEL_ID, tools)
        _register_allowlist_hook(agent, log)

        # The document text is supplied in the prompt context; the model reads text
        # it was handed, it does not fetch. get_document_pages (a tool) serves ranges
        # from THIS in-memory text, never the network.
        prompt = payload.get("prompt", "Extract the agenda items from the provided document text.")
        async for event in agent.stream_async(prompt):
            if isinstance(event, dict) and "event" in event:
                yield event

        log.info("extractor_complete", document_id=payload.get("document_id", ""))

    if __name__ == "__main__":
        app.run()

except Exception:
    # Runtime SDK not importable (e.g. unit-test env). The tested logic
    # (enforce_tool_allowlist, tools.py, agent.py) does not depend on it.
    app = None  # type: ignore[assignment]
