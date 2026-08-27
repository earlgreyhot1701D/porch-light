"""Porch Light — configuration module.

Production code. Reads environment variables, provides typed access.
Keeps the rest of the codebase free of os.environ calls.

Component is passed at the call site, never from the environment.
Model id comes from BEDROCK_MODEL_ID env var (never hardcoded).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from porchlight.log import VALID_COMPONENTS, compute_log_group


@dataclass(frozen=True)
class PorchlightConfig:
    """Typed configuration for a Porch Light agent run."""

    env: str
    """Deployment environment: dev | staging | prod."""

    aws_region: str
    """AWS region for Bedrock and CloudWatch."""

    model_id: str
    """Bedrock model identifier (from BEDROCK_MODEL_ID env var)."""

    component: str
    """Agent component: spike | hunter | extractor | watcher."""

    log_group: str
    """Computed CloudWatch log group: /porchlight/{env}/{component}."""


def load_config(component: str) -> PorchlightConfig:
    """Load configuration from environment variables.

    Args:
        component: The agent component name (spike, hunter, extractor, watcher).
                   Passed at the call site, not read from environment.

    Returns:
        PorchlightConfig with all fields populated.

    Raises:
        ValueError: If component is not in VALID_COMPONENTS.
        EnvironmentError: If a required env var is missing.
    """
    if component not in VALID_COMPONENTS:
        raise ValueError(
            f"Invalid component '{component}'. Must be one of: {sorted(VALID_COMPONENTS)}"
        )

    env = _require_env("ENV", default="dev")
    aws_region = _require_env("AWS_REGION", default="us-east-1")
    model_id = _require_env("BEDROCK_MODEL_ID")

    return PorchlightConfig(
        env=env,
        aws_region=aws_region,
        model_id=model_id,
        component=component,
        log_group=compute_log_group(env, component),
    )


def _require_env(name: str, default: str | None = None) -> str:
    """Read an environment variable or raise with a clear message.

    Args:
        name: The environment variable name.
        default: Optional default value. If None and var is missing, raises.

    Returns:
        The value of the environment variable.

    Raises:
        EnvironmentError: If the var is missing and no default is provided.
    """
    value = os.environ.get(name)
    if value is not None:
        return value
    if default is not None:
        return default
    raise EnvironmentError(
        f"Required environment variable '{name}' is not set. "
        f"Copy .env.example to .env and fill in the value."
    )
