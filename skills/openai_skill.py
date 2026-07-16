"""OpenAI skill: GPT API integration tools.

Provides tools to interact with OpenAI's GPT models for text generation.

Skill best practices:
  - Each tool function is an async generator yielding ToolChunk
  - ToolChunk.content uses [TextBlock(text=...)] format
  - Final chunk uses ToolChunk(state=SUCCESS/ERROR)
  - Proper type annotations and docstrings
  - API key loaded from environment variable

Requires:
  OPENAI_API_KEY in .env
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import FunctionTool, ToolChunk
from openai import OpenAI


def get_tools() -> list[FunctionTool]:
    """Return tools provided by the OpenAI skill."""
    return [
        FunctionTool(openai_chat),
    ]


async def openai_chat(
    prompt: str,
    model: str = "gpt-4o",
    system: str | None = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[ToolChunk, None]:
    """Send a message to OpenAI GPT and get a response.

    Use this tool to leverage GPT's capabilities for tasks that benefit
    from OpenAI's model strengths, such as code generation, structured
    output, or comparing outputs across different AI providers.

    Args:
        prompt: The user message to send to GPT.
        model: GPT model to use (default: gpt-4o).
        system: Optional system prompt to guide GPT's behavior.
        max_tokens: Maximum tokens in the response (default: 4096).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[TextBlock(text="OPENAI_API_KEY not set in .env")],
        )
        return

    try:
        client = OpenAI(api_key=api_key)

        messages: list[dict] = [{"role": "user", "content": prompt}]
        if system:
            messages.insert(0, {"role": "system", "content": system})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )

        result = response.choices[0].message.content or "(empty response)"

        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[
                TextBlock(
                    text=f"[GPT: {model}]\n{result}",
                ),
            ],
        )

    except Exception as e:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[TextBlock(text=f"OpenAI API error: {e}")],
        )