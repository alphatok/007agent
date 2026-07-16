"""Tests for app.config module."""
import os
from unittest.mock import patch

import pytest


class TestConfig:
    """Tests for Config and load_config."""

    def test_load_config_with_env(self) -> None:
        """Config should load values from environment variables."""
        from app.config import Config, load_config

        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "sk-test-key",
                "DEEPSEEK_MODEL": "deepseek-v4-pro",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            },
        ):
            config = load_config()
            assert config.deepseek_api_key == "sk-test-key"
            assert config.deepseek_model == "deepseek-v4-pro"
            assert config.deepseek_base_url == "https://api.deepseek.com"

    def test_load_config_defaults(self) -> None:
        """Config should use sensible defaults when env vars are missing."""
        from app.config import Config, load_config

        with patch.dict(
            os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True
        ):
            config = load_config()
            assert config.deepseek_model == "deepseek-v4-pro"
            assert config.deepseek_base_url == "https://api.deepseek.com"
            assert config.permission_mode == "bypass"
            assert config.chrome_mcp_enabled is True

    def test_config_is_dataclass(self) -> None:
        """Config should be a dataclass-like object with typed fields."""
        from app.config import Config

        config = Config(
            deepseek_api_key="sk-test",
            deepseek_model="test-model",
            deepseek_base_url="https://test.api",
            permission_mode="bypass",
            chrome_mcp_enabled=False,
        )
        assert isinstance(config.deepseek_api_key, str)
        assert isinstance(config.chrome_mcp_enabled, bool)