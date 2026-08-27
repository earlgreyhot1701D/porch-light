"""Porch Light — structured logging module.

Production code. All agents import this. Responsible for:
- Generating sortable run_ids
- Binding run context to contextvars (run_id, component, model_id)
- Routing stdlib logs through the same structlog processor chain
- Enforcing redaction: size-cap on extra fields, rejection of document content
- Emitting structured JSON, one event per line, to stdout

Why this module is allowed to fail open: §7 bans failing open for user-facing
results. Observability is not a user-facing result. A dropped log line is
acceptable; a fabricated or silently-degraded search result, match, or draft
is not. The logger never raises, never crashes the caller, and never suppresses
a user-facing error to protect itself.
"""

from __future__ import annotations

import logging
import secrets
import sys
from datetime import datetime, timezone
from typing import Any

import structlog

# --- Valid components (validated at bind time) ---
VALID_COMPONENTS = frozenset({"spike", "hunter", "extractor", "watcher"})

# --- Redaction configuration ---
# Maximum characters per extra field value before truncation.
# Rationale: 512 chars is enough for any reasonable log context (stack trace
# summary, short message). Anything longer is likely packet text leaking in.
EXTRA_FIELD_SIZE_CAP = 512

# Keys matching these substrings are always redacted (security.md: logs never
# contain packet text).
_REDACTED_KEY_PATTERNS = ("source_text", "packet_text", "document_content", "page_content")


def generate_run_id() -> str:
    """Generate a unique, sortable run identifier.

    Format: run_YYYYMMDDTHHMMSSZ_<8 lowercase alphanumeric>
    Example: run_20260823T143000Z_a1b2c3d4
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = secrets.token_hex(4)  # 4 bytes = 8 hex chars, always lowercase
    return f"run_{ts}_{suffix}"


def _redact_value(value: Any) -> Any:
    """Recursively redact a single value.

    - Dicts: check each key (case-insensitive) for document-content patterns,
      recurse into nested values.
    - Lists: recurse into each element.
    - Strings: apply size-cap.
    - Other scalars: convert to string and apply size-cap.

    Never raises; serialization issues fall back to repr().
    """
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            key_lower = k.lower() if isinstance(k, str) else str(k).lower()
            if any(pattern in key_lower for pattern in _REDACTED_KEY_PATTERNS):
                result[k] = "[redacted:document_content]"
            else:
                result[k] = _redact_value(v)
        return result

    if isinstance(value, list):
        return [_redact_value(item) for item in value]

    # Scalar: apply size-cap
    try:
        str_value = str(value) if not isinstance(value, str) else value
    except Exception:
        str_value = repr(value)

    if len(str_value) > EXTRA_FIELD_SIZE_CAP:
        return f"[truncated:{len(str_value)}]"

    return value


def _redact_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor that enforces redaction and size-cap rules.

    - Fields whose key contains a document-content pattern (case-insensitive)
      are replaced with a redaction marker.
    - Nested dicts and lists are recursed: any key at any depth matching a
      document-content pattern is redacted.
    - Fields exceeding EXTRA_FIELD_SIZE_CAP are truncated with a marker.
    - Never raises; serialization issues fall back to repr().
    """
    # Keys that are part of the core schema and should not be redacted/capped.
    _EXEMPT_KEYS = {"timestamp", "level", "component", "run_id", "message", "model_id", "event"}

    for key in list(event_dict.keys()):
        if key in _EXEMPT_KEYS:
            continue

        # Check top-level key for document-content pattern (case-insensitive)
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in _REDACTED_KEY_PATTERNS):
            event_dict[key] = "[redacted:document_content]"
            continue

        # Recurse into the value for nested redaction and size-cap
        event_dict[key] = _redact_value(event_dict[key])

    return event_dict


def bind_context(*, component: str, run_id: str, model_id: str | None = None) -> None:
    """Bind run_id, component, and model_id to contextvars.

    Configures structlog to route stdlib logging through the same processor
    chain, so third-party library logs (boto3, Strands internals) inherit
    the bound context.

    Raises ValueError if component not in VALID_COMPONENTS.
    """
    if component not in VALID_COMPONENTS:
        raise ValueError(
            f"Invalid component '{component}'. Must be one of: {sorted(VALID_COMPONENTS)}"
        )

    # Bind to structlog contextvars
    ctx: dict[str, Any] = {"run_id": run_id, "component": component}
    if model_id is not None:
        ctx["model_id"] = model_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**ctx)

    # Configure structlog with processors
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _redact_processor,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through structlog's ProcessorFormatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    # Root logger level is a security control, not just a noise preference.
    # Third-party libraries (boto3, botocore, urllib3) at DEBUG emit full HTTP
    # request and response bodies. At Spec 3+ those bodies contain packet text.
    # Our _redact_processor inspects extra fields on events WE emit; a boto3
    # debug record carries document content inside its message string, where
    # the redactor never looks. Root logger level is therefore the only control
    # preventing packet text from reaching CloudWatch via third-party logs.
    root_logger.setLevel(logging.INFO)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger.

    Context (run_id, component, model_id) is injected automatically from
    contextvars on every event.
    """
    return structlog.get_logger(name)


def compute_log_group(env: str, component: str) -> str:
    """Compute the CloudWatch log group path.

    Returns /porchlight/{env}/{component}.
    Validates component against VALID_COMPONENTS.
    """
    if component not in VALID_COMPONENTS:
        raise ValueError(
            f"Invalid component '{component}'. Must be one of: {sorted(VALID_COMPONENTS)}"
        )
    return f"/porchlight/{env}/{component}"
