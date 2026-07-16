"""Tests for skill system and individual skills."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentscope.tool import FunctionTool


class TestSkillDiscovery:
    """Tests for skill auto-discovery."""

    def test_discover_skills_returns_list(self) -> None:
        """discover_skills should return a list of tools."""
        from skills import discover_skills

        tools = discover_skills()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_discover_skills_are_function_tools(self) -> None:
        """All discovered tools should be FunctionTool instances."""
        from skills import discover_skills

        tools = discover_skills()
        for tool in tools:
            assert isinstance(tool, FunctionTool)

    def test_anthropic_skill_has_one_tool(self) -> None:
        """Anthropic skill should export exactly 1 tool."""
        from skills.anthropic_skill import get_tools

        tools = get_tools()
        assert len(tools) == 1
        assert isinstance(tools[0], FunctionTool)

    def test_openai_skill_has_one_tool(self) -> None:
        """OpenAI skill should export exactly 1 tool."""
        from skills.openai_skill import get_tools

        tools = get_tools()
        assert len(tools) == 1
        assert isinstance(tools[0], FunctionTool)

    def test_discover_skills_finds_both_skills(self) -> None:
        """discover_skills should find both anthropic and openai skills."""
        from skills import discover_skills

        tools = discover_skills()
        # Should have at least 2 tools (one from each skill)
        assert len(tools) >= 2


class TestAnthropicSkill:
    """Tests for Anthropic skill tools."""

    @pytest.mark.asyncio
    async def test_anthropic_chat_missing_api_key(self) -> None:
        """anthropic_chat should return error when API key is not set."""
        from skills.anthropic_skill import anthropic_chat

        # Ensure no API key is set
        with patch.dict(os.environ, {}, clear=True):
            chunks = []
            async for chunk in anthropic_chat(prompt="Hello"):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert "ANTHROPIC_API_KEY not set" in chunks[0].content[0].text

    @pytest.mark.asyncio
    async def test_anthropic_chat_success(self) -> None:
        """anthropic_chat should call Anthropic API and return response."""
        from skills.anthropic_skill import anthropic_chat

        # Mock the Anthropic client
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "Hello from Claude!"
        mock_response.content = [mock_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch(
                "skills.anthropic_skill.Anthropic",
                return_value=mock_client,
            ):
                chunks = []
                async for chunk in anthropic_chat(prompt="Hello"):
                    chunks.append(chunk)

        assert len(chunks) == 1
        text = chunks[0].content[0].text
        assert "[Claude:" in text
        assert "Hello from Claude!" in text

    @pytest.mark.asyncio
    async def test_anthropic_chat_with_system(self) -> None:
        """anthropic_chat should pass system prompt to API."""
        from skills.anthropic_skill import anthropic_chat

        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "Response"
        mock_response.content = [mock_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch(
                "skills.anthropic_skill.Anthropic",
                return_value=mock_client,
            ):
                chunks = []
                async for chunk in anthropic_chat(
                    prompt="Hello",
                    system="You are a helpful assistant.",
                ):
                    chunks.append(chunk)

        # Verify system prompt was passed
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_anthropic_chat_api_error(self) -> None:
        """anthropic_chat should return error on API failure."""
        from skills.anthropic_skill import anthropic_chat

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch(
                "skills.anthropic_skill.Anthropic",
                return_value=mock_client,
            ):
                chunks = []
                async for chunk in anthropic_chat(prompt="Hello"):
                    chunks.append(chunk)

        assert len(chunks) == 1
        assert "Anthropic API error" in chunks[0].content[0].text


class TestOpenAISkill:
    """Tests for OpenAI skill tools."""

    @pytest.mark.asyncio
    async def test_openai_chat_missing_api_key(self) -> None:
        """openai_chat should return error when API key is not set."""
        from skills.openai_skill import openai_chat

        with patch.dict(os.environ, {}, clear=True):
            chunks = []
            async for chunk in openai_chat(prompt="Hello"):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert "OPENAI_API_KEY not set" in chunks[0].content[0].text

    @pytest.mark.asyncio
    async def test_openai_chat_success(self) -> None:
        """openai_chat should call OpenAI API and return response."""
        from skills.openai_skill import openai_chat

        mock_choice = MagicMock()
        mock_choice.message.content = "Hello from GPT!"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "skills.openai_skill.OpenAI",
                return_value=mock_client,
            ):
                chunks = []
                async for chunk in openai_chat(prompt="Hello"):
                    chunks.append(chunk)

        assert len(chunks) == 1
        text = chunks[0].content[0].text
        assert "[GPT:" in text
        assert "Hello from GPT!" in text

    @pytest.mark.asyncio
    async def test_openai_chat_with_system(self) -> None:
        """openai_chat should pass system prompt to API."""
        from skills.openai_skill import openai_chat

        mock_choice = MagicMock()
        mock_choice.message.content = "Response"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "skills.openai_skill.OpenAI",
                return_value=mock_client,
            ):
                chunks = []
                async for chunk in openai_chat(
                    prompt="Hello",
                    system="You are a helpful assistant.",
                ):
                    chunks.append(chunk)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}

    @pytest.mark.asyncio
    async def test_openai_chat_api_error(self) -> None:
        """openai_chat should return error on API failure."""
        from skills.openai_skill import openai_chat

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch(
                "skills.openai_skill.OpenAI",
                return_value=mock_client,
            ):
                chunks = []
                async for chunk in openai_chat(prompt="Hello"):
                    chunks.append(chunk)

        assert len(chunks) == 1
        assert "OpenAI API error" in chunks[0].content[0].text