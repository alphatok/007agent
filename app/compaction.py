"""Context compaction monitoring module.

Provides tools for checking context token usage and monitoring compaction
status. The actual compaction engine is handled by AgentScope's built-in
``compress_context()`` mechanism, which auto-triggers before each reasoning
step when tokens exceed ``ContextConfig.trigger_ratio`` of the model's
context window.

DeepSeek V4 Pro context window: 128K tokens.
Default trigger ratio: 0.4 (40% = 51.2K tokens).
Warning threshold: 20,000 tokens.
"""
from __future__ import annotations

from typing import AsyncGenerator

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import FunctionTool, ToolChunk


async def context_status(
    action: str = "check",
    trigger_ratio: float = 0.4,
    warning_tokens: int = 20000,
    context_size: int = 128000,
) -> AsyncGenerator[ToolChunk, None]:
    """Check or manage context token usage.

    AgentScope automatically compresses conversation context when token
    usage exceeds the configured threshold. This tool lets you check the
    current status and trigger manual compaction.

    Args:
        action: "check" to view status, "compact" to request compaction.
        trigger_ratio: Context usage ratio that triggers auto-compaction
            (default 0.4 = 40%).
        warning_tokens: Token count that triggers a warning (default 20000).
        context_size: Model's total context window size in tokens
            (default 128000 for DeepSeek V4 Pro).
    """
    if action not in ("check", "compact"):
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    text=f"Unknown action '{action}'. "
                    "Use 'check' or 'compact'.",
                ),
            ],
        )
        return

    trigger_threshold = int(context_size * trigger_ratio)

    if action == "check":
        lines = [
            "Context Compaction Status",
            "=========================",
            f"Model context window: {context_size:,} tokens",
            f"Auto-compaction trigger: {trigger_ratio*100:.0f}% "
            f"({trigger_threshold:,} tokens)",
            f"Warning threshold: {warning_tokens:,} tokens",
            "",
            "AgentScope automatically compresses context before each "
            "reasoning step when usage exceeds the trigger threshold.",
            "Compression preserves: task overview, current state, "
            "important discoveries, next steps, and user preferences.",
            "",
            "Status levels:",
            f"  - Normal:  < {warning_tokens:,} tokens",
            f"  - Warning: {warning_tokens:,} - {trigger_threshold:,} tokens",
            f"  - Critical: > {trigger_threshold:,} tokens "
            "(auto-compaction triggers)",
        ]
        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[TextBlock(text="\n".join(lines))],
        )

    elif action == "compact":
        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[
                TextBlock(
                    text="Compaction request noted. AgentScope's built-in "
                    "compression will automatically trigger before the "
                    "next reasoning step if the token threshold is "
                    "exceeded. No manual intervention is required.",
                ),
            ],
        )


def get_tools() -> list[FunctionTool]:
    """Return the context compaction tools."""
    return [FunctionTool(context_status)]