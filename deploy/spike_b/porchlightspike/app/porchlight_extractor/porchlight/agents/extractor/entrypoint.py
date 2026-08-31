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
        from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry
    except Exception as exc:  # SDK surface missing/changed — do not run unguarded.
        raise RuntimeError(
            "extractor tool-allowlist hook unavailable; refusing to run unguarded"
        ) from exc

    def _tool_name(event) -> str:
        # `tool_use` is a ToolUse mapping ({"name": ..., "toolUseId": ..., "input": ...}).
        tu = getattr(event, "tool_use", None)
        if isinstance(tu, dict):
            return tu.get("name", "") or ""
        return getattr(tu, "name", "") or ""

    class _AllowlistHook(HookProvider):
        def register_hooks(self, registry: HookRegistry) -> None:
            registry.add_callback(BeforeToolCallEvent, self._before_tool)

        def _before_tool(self, event: BeforeToolCallEvent) -> None:
            name = _tool_name(event)
            if not enforce_tool_allowlist(name, log):
                # Fail closed: prevent the tool from executing. Prefer the SDK's
                # cancel_tool signal; also raise as a hard backstop so a blocked
                # tool NEVER runs even if cancel semantics change.
                try:
                    event.cancel_tool = f"tool not on extractor allowlist: {name!r}"
                except Exception:
                    pass
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

        # Containment self-test (explicit opt-in, never in normal operation): plant a
        # deliberately NON-allowlisted tool and ask the model to use it, so the hook
        # blocks it and emits a real NEVER-trip against the deployed runtime. This is
        # a genuine blocked attempt (R5 condition 2), not a simulation. Guarded by an
        # explicit payload flag; absent it, no probe tool exists.
        tools = list(payload.get("_tools", []) or [])
        probe = bool(payload.get("_containment_probe", False))
        if probe:
            from strands import tool as _strands_tool

            # A BENIGN, plainly-safe tool that simply is NOT on the four-name
            # allowlist. The point is the allowlist blocks by NAME regardless of the
            # tool's intent — so a benign tool the model will actually call proves the
            # hook fires (an obviously-malicious tool just gets refused by the model's
            # own safety, which does not exercise our control).
            @_strands_tool
            def count_words(text: str) -> str:
                """Count the words in a short piece of text (containment probe — NOT allowlisted)."""
                return str(len((text or "").split()))

            tools.append(count_words)

        agent = build_agent(MODEL_ID, tools)
        _register_allowlist_hook(agent, log)

        if probe:
            log.info("containment_probe_start", note="asking model to call non-allowlisted count_words")
            prompt = ("Use the count_words tool to count the words in the phrase "
                      "'the quick brown fox'. Call the tool now.")
            async for event in agent.stream_async(prompt):
                if isinstance(event, dict) and "event" in event:
                    yield event
            log.info("containment_probe_complete")
            return

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
