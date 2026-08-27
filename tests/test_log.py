"""Property-based tests for the Porch Light logging module.

Production code: src/porchlight/log.py
Test library: Hypothesis
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from porchlight.log import (
    EXTRA_FIELD_SIZE_CAP,
    VALID_COMPONENTS,
    _redact_processor,
    bind_context,
    compute_log_group,
    generate_run_id,
    get_logger,
)

# --- Strategies ---

valid_components = st.sampled_from(sorted(VALID_COMPONENTS))
valid_envs = st.sampled_from(["dev", "staging", "prod"])
valid_levels = st.sampled_from(["debug", "info", "warning", "error"])
run_id_pattern = re.compile(r"^run_\d{8}T\d{6}Z_[a-z0-9]{8}$")


# =============================================================================
# Feature: 0-stack-proof, Property 1: Run ID format validity
# =============================================================================


class TestRunIdFormatValidity:
    """For any invocation of generate_run_id(), the returned string SHALL match
    the pattern run_\\d{8}T\\d{6}Z_[a-z0-9]{8}, the timestamp portion SHALL
    represent a valid UTC datetime, and the random suffix SHALL be exactly 8
    lowercase alphanumeric characters.
    """

    @given(st.integers(min_value=0, max_value=999))
    @settings(max_examples=200)
    def test_format_matches_pattern(self, _: int) -> None:
        rid = generate_run_id()
        assert run_id_pattern.match(rid), f"run_id '{rid}' does not match expected pattern"

    @given(st.integers(min_value=0, max_value=999))
    @settings(max_examples=200)
    def test_timestamp_is_valid_utc(self, _: int) -> None:
        rid = generate_run_id()
        # Extract timestamp portion: between first _ and second _
        parts = rid.split("_")
        ts_str = parts[1]  # YYYYMMDDTHHMMSSZ
        # Parse it
        parsed = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ")
        # Should be close to now (within 5 seconds)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = abs((now - parsed).total_seconds())
        assert delta < 5, f"Timestamp {ts_str} is not close to current UTC time"

    @given(st.integers(min_value=0, max_value=999))
    @settings(max_examples=200)
    def test_suffix_is_8_lowercase_alphanumeric(self, _: int) -> None:
        rid = generate_run_id()
        suffix = rid.split("_")[2]
        assert len(suffix) == 8
        assert suffix == suffix.lower()
        assert suffix.isalnum()


# =============================================================================
# Feature: 0-stack-proof, Property 4: Run ID uniqueness
# =============================================================================


class TestRunIdUniqueness:
    """For any set of 1000 sequential calls to generate_run_id(), no two
    returned values SHALL be identical.
    """

    def test_1000_ids_are_unique(self) -> None:
        ids = [generate_run_id() for _ in range(1000)]
        assert len(set(ids)) == len(ids), "Duplicate run_id detected in 1000 sequential calls"


# =============================================================================
# Feature: 0-stack-proof, Property 2: Structured log event completeness
# =============================================================================


class TestStructuredLogEventCompleteness:
    """For any valid combination of level, component, run_id, message, and
    optional model_id, formatting the event SHALL produce a single line of
    valid JSON containing at minimum the fields timestamp, level, component,
    run_id, and message with their provided values, plus model_id when supplied.
    """

    @given(
        component=valid_components,
        message=st.text(min_size=1, max_size=100),
        model_id=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        level=valid_levels,
    )
    @settings(max_examples=200)
    def test_event_contains_required_fields(
        self, component: str, message: str, model_id: str | None, level: str
    ) -> None:
        assume("\n" not in message and "\r" not in message)
        assume(model_id is None or ("\n" not in model_id and "\r" not in model_id))

        rid = generate_run_id()
        buf = StringIO()

        with patch("sys.stdout", buf):
            bind_context(component=component, run_id=rid, model_id=model_id)
            # Level set to DEBUG locally because the application default is INFO
            # as a security control (third-party DEBUG records carry unredacted
            # request bodies). Do not "fix" the app default to match this test.
            import logging as _logging
            _logging.getLogger().setLevel(_logging.DEBUG)
            log = get_logger("test")
            getattr(log, level)(message)

        output = buf.getvalue().strip()
        assert output, "No log output produced"

        # Should be valid JSON on a single line
        lines = output.split("\n")
        # Take the last non-empty line (structlog may emit warnings on first configure)
        json_line = [l for l in lines if l.strip()][-1]
        event = json.loads(json_line)

        assert event["run_id"] == rid
        assert event["component"] == component
        assert event["level"] == level
        assert "timestamp" in event
        # Message appears as "event" key in structlog
        assert event["event"] == message

        if model_id is not None:
            assert event["model_id"] == model_id
        else:
            assert "model_id" not in event


# =============================================================================
# Feature: 0-stack-proof, Property 3: Log group name derivation
# =============================================================================


class TestLogGroupNameDerivation:
    """For any valid environment name and component name, the log group path
    SHALL equal /porchlight/{env}/{component} with no leading/trailing
    whitespace and no double slashes.
    """

    @given(env=valid_envs, component=valid_components)
    @settings(max_examples=200)
    def test_log_group_format(self, env: str, component: str) -> None:
        result = compute_log_group(env, component)
        expected = f"/porchlight/{env}/{component}"
        assert result == expected
        assert result == result.strip()
        assert "//" not in result

    @given(component=st.text(min_size=1, max_size=20).filter(lambda x: x not in VALID_COMPONENTS))
    @settings(max_examples=50)
    def test_invalid_component_raises(self, component: str) -> None:
        with pytest.raises(ValueError):
            compute_log_group("dev", component)


# =============================================================================
# Feature: 0-stack-proof, Property 5: Redaction and size-cap enforcement
# =============================================================================


class TestRedactionAndSizeCap:
    """For any extra field value exceeding the size cap (512 characters), or
    for any extra field whose key matches a document-content pattern, the
    emitted log event SHALL contain a truncation or omission marker rather
    than the original content.
    """

    @given(
        value=st.text(min_size=EXTRA_FIELD_SIZE_CAP + 1, max_size=EXTRA_FIELD_SIZE_CAP + 500),
    )
    @settings(max_examples=100)
    def test_oversized_field_is_truncated(self, value: str) -> None:
        event_dict = {"timestamp": "t", "level": "info", "event": "test", "big_field": value}
        result = _redact_processor(None, "info", event_dict)
        assert result["big_field"] == f"[truncated:{len(value)}]"

    @given(
        key=st.sampled_from(["source_text", "my_packet_text", "document_content_raw", "page_content_full"]),
        value=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_document_content_key_is_redacted(self, key: str, value: str) -> None:
        event_dict = {"timestamp": "t", "level": "info", "event": "test", key: value}
        result = _redact_processor(None, "info", event_dict)
        assert result[key] == "[redacted:document_content]"

    @given(
        key=st.text(min_size=1, max_size=30).filter(
            lambda k: not any(p in k for p in ("source_text", "packet_text", "document_content", "page_content"))
            and k not in ("timestamp", "level", "component", "run_id", "message", "model_id", "event")
        ),
        value=st.text(max_size=EXTRA_FIELD_SIZE_CAP),
    )
    @settings(max_examples=100)
    def test_small_safe_field_passes_through(self, key: str, value: str) -> None:
        event_dict = {"timestamp": "t", "level": "info", "event": "test", key: value}
        result = _redact_processor(None, "info", event_dict)
        assert result[key] == value

    @given(
        key=st.sampled_from(["Source_Text", "PACKET_TEXT", "Document_Content", "PAGE_CONTENT"]),
        value=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_mixed_case_keys_are_redacted(self, key: str, value: str) -> None:
        """Case-insensitive key matching catches mixed-case variants."""
        event_dict = {"timestamp": "t", "level": "info", "event": "test", key: value}
        result = _redact_processor(None, "info", event_dict)
        assert result[key] == "[redacted:document_content]"

    @given(
        inner_value=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_nested_dict_redaction(self, inner_value: str) -> None:
        """Document-content keys inside nested dicts are caught."""
        event_dict = {
            "timestamp": "t",
            "level": "info",
            "event": "test",
            "data": {"packet_text": inner_value, "safe_key": "visible"},
        }
        result = _redact_processor(None, "info", event_dict)
        assert result["data"]["packet_text"] == "[redacted:document_content]"
        assert result["data"]["safe_key"] == "visible"

    @given(
        inner_value=st.text(min_size=EXTRA_FIELD_SIZE_CAP + 1, max_size=EXTRA_FIELD_SIZE_CAP + 200),
    )
    @settings(max_examples=100)
    def test_nested_list_size_cap(self, inner_value: str) -> None:
        """Oversized strings inside lists are truncated."""
        event_dict = {
            "timestamp": "t",
            "level": "info",
            "event": "test",
            "items": [inner_value, "short"],
        }
        result = _redact_processor(None, "info", event_dict)
        assert result["items"][0] == f"[truncated:{len(inner_value)}]"
        assert result["items"][1] == "short"

    @given(
        inner_value=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_deeply_nested_redaction(self, inner_value: str) -> None:
        """Keys at arbitrary depth are caught."""
        event_dict = {
            "timestamp": "t",
            "level": "info",
            "event": "test",
            "outer": {"middle": {"Document_Content_Here": inner_value}},
        }
        result = _redact_processor(None, "info", event_dict)
        assert result["outer"]["middle"]["Document_Content_Here"] == "[redacted:document_content]"


# =============================================================================
# Unit tests (specific examples)
# =============================================================================


class TestComponentValidation:
    """Component must be validated; invalid values raise immediately."""

    def test_valid_components_accepted(self) -> None:
        for comp in VALID_COMPONENTS:
            rid = generate_run_id()
            bind_context(component=comp, run_id=rid)  # Should not raise

    def test_invalid_component_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            bind_context(component="typo", run_id=generate_run_id())

    def test_empty_component_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            bind_context(component="", run_id=generate_run_id())


class TestLoggerLevelSecurity:
    """Root logger level is a security control preventing packet text egress.

    Third-party DEBUG records (boto3, botocore, urllib3) carry full HTTP
    request/response bodies in their message string, where field-level
    redaction cannot reach. The root logger and known-noisy third-party
    loggers must be at INFO or above.
    """

    def test_root_logger_is_info_after_bind(self) -> None:
        import logging as _logging
        bind_context(component="spike", run_id=generate_run_id())
        assert _logging.getLogger().level >= _logging.INFO

    def test_botocore_logger_is_info_or_above(self) -> None:
        import logging as _logging
        bind_context(component="spike", run_id=generate_run_id())
        botocore_level = _logging.getLogger("botocore").getEffectiveLevel()
        assert botocore_level >= _logging.INFO

    def test_urllib3_logger_is_info_or_above(self) -> None:
        import logging as _logging
        bind_context(component="spike", run_id=generate_run_id())
        urllib3_level = _logging.getLogger("urllib3").getEffectiveLevel()
        assert urllib3_level >= _logging.INFO
