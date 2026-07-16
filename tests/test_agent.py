"""Tests for app.agent module."""
import os
from unittest.mock import MagicMock, patch

import pytest


class TestBuildAgent:
    """Tests for build_agent factory function."""

    def test_build_agent_returns_agent(self) -> None:
        """Should return a configured Agent instance."""
        from app.agent import build_agent
        from app.config import Config

        config = Config(
            deepseek_api_key="sk-test",
            chrome_mcp_enabled=False,
        )
        mock_toolkit = MagicMock()

        agent = build_agent(config, mock_toolkit)
        assert agent is not None
        assert agent.name == "AgentScope"

    def test_build_agent_uses_deepseek_model(self) -> None:
        """Agent should be configured with DeepSeekChatModel."""
        from app.agent import build_agent
        from app.config import Config
        from agentscope.model import DeepSeekChatModel

        config = Config(
            deepseek_api_key="sk-test",
            deepseek_model="deepseek-v4-pro",
            chrome_mcp_enabled=False,
        )
        mock_toolkit = MagicMock()

        agent = build_agent(config, mock_toolkit)
        assert isinstance(agent.model, DeepSeekChatModel)

    def test_build_agent_has_system_prompt(self) -> None:
        """Agent should have a non-empty system prompt."""
        from app.agent import build_agent
        from app.config import Config

        config = Config(
            deepseek_api_key="sk-test",
            chrome_mcp_enabled=False,
        )
        mock_toolkit = MagicMock()

        agent = build_agent(config, mock_toolkit)
        assert len(agent._system_prompt) > 0