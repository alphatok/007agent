"""Tests for app.agent module."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBuildAgent:
    """Tests for build_agent factory function."""

    @pytest.mark.asyncio
    async def test_build_agent_returns_agent(self) -> None:
        """Should return a configured Agent instance."""
        from app.agent import build_agent
        from app.config import Config

        config = Config(
            deepseek_api_key="sk-test",
            chrome_mcp_enabled=False,
        )
        mock_toolkit = MagicMock()
        mock_toolkit.get_skill_instructions = AsyncMock(return_value=None)

        agent = await build_agent(config, mock_toolkit)
        assert agent is not None
        assert agent.name == "AgentScope"

    @pytest.mark.asyncio
    async def test_build_agent_uses_deepseek_model(self) -> None:
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
        mock_toolkit.get_skill_instructions = AsyncMock(return_value=None)

        agent = await build_agent(config, mock_toolkit)
        assert isinstance(agent.model, DeepSeekChatModel)

    @pytest.mark.asyncio
    async def test_build_agent_has_system_prompt(self) -> None:
        """Agent should have a non-empty system prompt."""
        from app.agent import build_agent
        from app.config import Config

        config = Config(
            deepseek_api_key="sk-test",
            chrome_mcp_enabled=False,
        )
        mock_toolkit = MagicMock()
        mock_toolkit.get_skill_instructions = AsyncMock(return_value=None)

        agent = await build_agent(config, mock_toolkit)
        assert len(agent._system_prompt) > 0

    @pytest.mark.asyncio
    async def test_build_agent_injects_skill_instructions(self) -> None:
        """Agent system prompt should include skill instructions when available."""
        from app.agent import build_agent, SYSTEM_PROMPT
        from app.config import Config

        config = Config(
            deepseek_api_key="sk-test",
            chrome_mcp_enabled=False,
        )
        mock_toolkit = MagicMock()
        mock_toolkit.get_skill_instructions = AsyncMock(
            return_value="<agent-skills>code-review</agent-skills>",
        )

        agent = await build_agent(config, mock_toolkit)
        assert "code-review" in agent._system_prompt
        assert SYSTEM_PROMPT in agent._system_prompt