"""Anthropic skill: Claude API integration tools.

Provides tools to interact with Anthropic's Claude models for text generation.

Skill best practices:
  - Each tool function is an async generator yielding ToolChunk
  - ToolChunk.content uses [TextBlock(text=...)] format
  - Final chunk uses ToolChunk(state=SUCCESS/ERROR)
  - Proper type annotations and docstrings
  - API key loaded from environment variable

Requires:
  ANTHROPIC_API_KEY in .env
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

from anthropic import Anthropic
from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import FunctionTool, ToolChunk


def get_tools() -> list[FunctionTool]:
    """Return tools provided by the Anthropic skill."""
    return [
        FunctionTool(anthropic_chat),
    ]


async def anthropic_chat(
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    system: str | None = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[ToolChunk, None]:
    """Send a message to Anthropic Claude and get a response.

    Use this tool to leverage Claude's capabilities for tasks that benefit
    from Anthropic's model strengths, such as long-form content generation,
    nuanced reasoning, or comparing outputs across different AI providers.

    Args:
        prompt: The user message to send to Claude.
        model: Claude model to use (default: claude-sonnet-4-5-20250929).
        system: Optional system prompt to guide Claude's behavior.
        max_tokens: Maximum tokens in the response (default: 4096).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[TextBlock(text="ANTHROPIC_API_KEY not set in .env")],
        )
        return

    try:
        client = Anthropic(api_key=api_key)

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)

        # Extract text from response content blocks
        text_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)

        result = "\n".join(text_parts) if text_parts else "(empty response)"

        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[
                TextBlock(
                    text=f"[Claude: {model}]\n{result}",
                ),
            ],
        )

    except Exception as e:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[TextBlock(text=f"Anthropic API error: {e}")],
        )