"""Tests for app.compaction module."""
import pytest


class TestContextStatusTool:
    """Tests for the context_status FunctionTool."""

    @pytest.mark.asyncio
    async def test_context_status_check_returns_success(self) -> None:
        """context_status("check") should return SUCCESS with status info."""
        from app.compaction import context_status

        chunks = []
        async for chunk in context_status(action="check"):
            chunks.append(chunk)

        assert len(chunks) == 1
        from agentscope.message import ToolResultState

        assert chunks[0].state == ToolResultState.SUCCESS
        text = chunks[0].content[0].text
        assert "Context Compaction Status" in text
        assert "Model context window" in text
        assert "Auto-compaction trigger" in text
        assert "Warning threshold" in text

    @pytest.mark.asyncio
    async def test_context_status_compact_returns_success(self) -> None:
        """context_status("compact") should return SUCCESS."""
        from app.compaction import context_status

        chunks = []
        async for chunk in context_status(action="compact"):
            chunks.append(chunk)

        assert len(chunks) == 1
        from agentscope.message import ToolResultState

        assert chunks[0].state == ToolResultState.SUCCESS
        assert "compression" in chunks[0].content[0].text.lower()

    @pytest.mark.asyncio
    async def test_context_status_unknown_action_returns_error(self) -> None:
        """context_status("invalid") should return ERROR."""
        from app.compaction import context_status

        chunks = []
        async for chunk in context_status(action="invalid"):
            chunks.append(chunk)

        assert len(chunks) == 1
        from agentscope.message import ToolResultState

        assert chunks[0].state == ToolResultState.ERROR
        assert "Unknown action" in chunks[0].content[0].text

    @pytest.mark.asyncio
    async def test_context_status_custom_thresholds(self) -> None:
        """context_status should reflect custom trigger_ratio and warning_tokens."""
        from app.compaction import context_status

        chunks = []
        async for chunk in context_status(
            action="check",
            trigger_ratio=0.5,
            warning_tokens=30000,
            context_size=100000,
        ):
            chunks.append(chunk)

        text = chunks[0].content[0].text
        assert "100,000 tokens" in text
        assert "50%" in text
        assert "50,000 tokens" in text
        assert "30,000 tokens" in text

    @pytest.mark.asyncio
    async def test_context_status_default_values(self) -> None:
        """context_status should use default values (128K, 0.4, 20000)."""
        from app.compaction import context_status

        chunks = []
        async for chunk in context_status(action="check"):
            chunks.append(chunk)

        text = chunks[0].content[0].text
        assert "128,000 tokens" in text
        assert "40%" in text
        assert "51,200 tokens" in text
        assert "20,000 tokens" in text


class TestGetTools:
    """Tests for get_tools() function."""

    def test_get_tools_returns_list(self) -> None:
        """get_tools should return a list of FunctionTool."""
        from app.compaction import get_tools

        tools = get_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1
        from agentscope.tool import FunctionTool

        assert isinstance(tools[0], FunctionTool)


class TestConfigCompaction:
    """Tests for compaction configuration."""

    def test_config_has_compaction_fields(self) -> None:
        """Config should have compaction_trigger_ratio and warning fields."""
        from app.config import Config

        config = Config(deepseek_api_key="sk-test")
        assert config.compaction_trigger_ratio == 0.4
        assert config.compaction_warning_tokens == 20000

    def test_agent_has_context_config(self) -> None:
        """Agent should have context_config with correct trigger_ratio."""
        from app.agent import build_agent
        from app.config import Config
        from unittest.mock import AsyncMock, MagicMock

        config = Config(
            deepseek_api_key="sk-test",
            chrome_mcp_enabled=False,
        )
        mock_toolkit = MagicMock()
        mock_toolkit.get_skill_instructions = AsyncMock(return_value=None)

        import asyncio

        agent = asyncio.run(build_agent(config, mock_toolkit))
        assert agent.context_config is not None
        assert agent.context_config.trigger_ratio == 0.4