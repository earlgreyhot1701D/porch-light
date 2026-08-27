"""Unit tests for the Porch Light config module."""

from __future__ import annotations

import os

import pytest

from porchlight.config import load_config, PorchlightConfig


class TestLoadConfig:
    """Tests for load_config()."""

    def test_loads_with_all_vars_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("AWS_REGION", "us-west-2")  # non-default, proves env var is read
        monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

        config = load_config("spike")

        assert config.env == "staging"
        assert config.aws_region == "us-west-2"
        assert config.model_id == "amazon.nova-lite-v1:0"
        assert config.component == "spike"
        assert config.log_group == "/porchlight/staging/spike"

    def test_uses_defaults_for_env_and_region(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

        config = load_config("hunter")

        assert config.env == "dev"
        assert config.aws_region == "us-east-1"
        assert config.component == "hunter"

    def test_missing_model_id_raises_with_var_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

        with pytest.raises(EnvironmentError, match="BEDROCK_MODEL_ID"):
            load_config("spike")

    def test_invalid_component_raises_valueerror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test")

        with pytest.raises(ValueError, match="Invalid component"):
            load_config("invalid_name")

    def test_config_is_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test")

        config = load_config("watcher")
        with pytest.raises(Exception):  # FrozenInstanceError
            config.env = "prod"  # type: ignore[misc]
