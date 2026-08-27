"""Spike A tools — two trivial tools to prove the Strands SDK tool-calling loop.

THROWAWAY code. Proves the SDK works locally, then stops mattering.
"""

from __future__ import annotations

from datetime import datetime, timezone

from strands import tool


@tool
def hello_tool(name: str) -> str:
    """Returns a greeting for the given name."""
    return f"Hello, {name}!"


@tool
def time_tool() -> str:
    """Returns the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()
