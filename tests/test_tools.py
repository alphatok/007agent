"""Tests for app.tools module."""
import os
from unittest.mock import patch

import pytest


class TestBuildToolkit:
    """Tests for build_toolkit factory function."""

    @pytest.mark.asyncio
    async def test_build_toolkit_without_mcp(self) -> None:
        """Should return Toolkit with built-in tools, no MCP."""
        from app.config import Config
        from app.tools import build_toolkit

        with patch.dict(
            os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True
        ):
            config = Config(
                deepseek_api_key="sk-test",
                chrome_mcp_enabled=False,
            )
            toolkit = await build_toolkit(config)
            assert toolkit is not None
            # Built-in tools should be in the first tool group
            basic_group = toolkit.tool_groups[0]
            tool_names = [t.name for t in basic_group.tools]
            assert "Bash" in tool_names
            assert "Read" in tool_names
            assert "Write" in tool_names

    @pytest.mark.asyncio
    async def test_build_toolkit_with_mcp(self) -> None:
        """Should return Toolkit with MCP disabled (no npx in CI)."""
        from app.config import Config
        from app.tools import build_toolkit

        config = Config(
            deepseek_api_key="sk-test",
            chrome_mcp_enabled=False,
        )
        toolkit = await build_toolkit(config)
        assert toolkit is not None

    def test_builtin_tool_count(self) -> None:
        """Should register exactly 12 built-in tools (10 core + web_search + context_status)."""
        from app.tools import BUILTIN_TOOLS

        assert len(BUILTIN_TOOLS) == 12
        expected = {
            "Bash", "Read", "Write", "Edit", "Glob", "Grep",
            "TaskCreate", "TaskGet", "TaskList", "TaskUpdate",
        }
        class_names = {t.__class__.__name__ for t in BUILTIN_TOOLS}
        assert expected.issubset(class_names)
        # Two FunctionTool wrappers: web_search + context_status
        function_tool_count = sum(
            1 for t in BUILTIN_TOOLS if t.__class__.__name__ == "FunctionTool"
        )
        assert function_tool_count == 2