"""Tool registration module.

Provides all built-in tools, search capability, skill system, and optional
Chrome DevTools MCP integration.

Skill system has two layers:
  - Tool Skills: Python modules in skills/ with get_tools() (auto-discovered)
  - Instruction Skills: SKILL.md files in skills/*/ (loaded via LocalSkillLoader)
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator

from agentscope.mcp import MCPClient
from agentscope.mcp._config import StdioMCPConfig
from agentscope.message import TextBlock, ToolResultState
from agentscope.skill import LocalSkillLoader
from agentscope.tool import (
    Bash,
    Edit,
    FunctionTool,
    Glob,
    Grep,
    Read,
    TaskCreate,
    TaskGet,
    TaskList,
    TaskUpdate,
    Toolkit,
    ToolChunk,
    Write,
)

from app.compaction import get_tools as get_compaction_tools
from app.config import Config
from app.memory_tool import get_memory_tools
from app.retry import retry_on_failure
from app.search import web_fetch, web_search
from app.subagent import get_tools as get_subagent_tools
from app.task_planner import plan_task
from skills import discover_skills

if TYPE_CHECKING:
    from app.task_manager import TaskManager

# Module-level reference for tool access to task_manager
_task_manager: "TaskManager | None" = None


def set_task_manager(tm: "TaskManager") -> None:
    """Set the global task manager for tool access."""
    global _task_manager
    _task_manager = tm


async def report_progress(
    progress: int,
    current_step: str,
    step_result: str = "",
) -> AsyncGenerator[ToolChunk, None]:
    """Report task progress. Use this during long-running tasks to update progress.

    Args:
        progress: Progress percentage (0-100).
        current_step: Description of current step.
        step_result: Optional result of the completed step.
    """
    if _task_manager is None:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    text="[FAIL] Task manager not initialized",
                ),
            ],
        )
        return

    yield ToolChunk(
        state=ToolResultState.RUNNING,
        content=[
            TextBlock(
                text=f"[Tool] Progress: {progress}% - {current_step}",
            ),
        ],
    )

    # Push progress to the queue for SSE streaming
    # We need to know which task_id to update. The task_manager's
    # progress queue is accessed via the current task context.
    # For now, update progress on the task record.
    result_text = f"Progress: {progress}% - {current_step}"
    if step_result:
        result_text += f"\nResult: {step_result}"

    yield ToolChunk(
        state=ToolResultState.SUCCESS,
        content=[
            TextBlock(text=result_text),
        ],
    )


# Global dicts for user response events (ask_user tool)
_user_response_events: dict[str, asyncio.Event] = {}
_user_responses: dict[str, str] = {}
_user_questions: dict[str, dict] = {}


async def ask_user(
    question: str,
    options: list[str] | None = None,
) -> AsyncGenerator[ToolChunk, None]:
    """Pause a long-running task to ask the user a critical decision question.

    ONLY use this tool during complex multi-step tasks when you encounter a
    genuine decision point that requires human judgment (e.g., choosing
    between two implementation approaches, confirming a risky operation).

    DO NOT use this tool for:
    - Simple greetings, casual conversation, or small talk
    - Straightforward questions the user asks directly
    - Clarifying what the user meant (just ask in your text reply)
    - Any situation where you can proceed without user input

    Args:
        question: The question to ask the user
        options: Optional list of options for the user to choose from
    """
    event = asyncio.Event()
    task_id = f"user-{id(event)}"

    _user_response_events[task_id] = event
    _user_questions[task_id] = {
        "question": question,
        "options": options or [],
    }

    options_text = ""
    if options:
        options_text = "\nOptions: " + ", ".join(options)

    yield ToolChunk(
        task_id=task_id,
        state=ToolResultState.RUNNING,
        content=[TextBlock(text=f"⏸ Waiting for user input...\nQ: {question}{options_text}")],
    )

    # Wait for user response with 5-minute timeout
    try:
        await asyncio.wait_for(event.wait(), timeout=300)
        response = _user_responses.get(task_id, "No response")
    except asyncio.TimeoutError:
        response = "__timeout__"

    # Cleanup
    _user_response_events.pop(task_id, None)
    _user_responses.pop(task_id, None)
    _user_questions.pop(task_id, None)

    if response == "__timeout__":
        yield ToolChunk(
            task_id=task_id,
            state=ToolResultState.ERROR,
            content=[TextBlock(text="User did not respond within 5 minutes. Task timed out.")],
        )
    else:
        yield ToolChunk(
            task_id=task_id,
            state=ToolResultState.SUCCESS,
            content=[TextBlock(text=f"User response: {response}")],
            metadata={"user_response": response},
        )


def set_user_response(task_id: str, response: str) -> bool:
    """Set the user's response and trigger the waiting event."""
    if task_id in _user_response_events:
        _user_responses[task_id] = response
        _user_response_events[task_id].set()
        return True
    return False


def get_pending_questions() -> dict[str, dict]:
    """Get all pending questions waiting for user input."""
    return dict(_user_questions)


# All built-in tools available to the agent
BUILTIN_TOOLS = [
    Bash(),
    Read(),
    Write(),
    Edit(),
    Glob(),
    Grep(),
    TaskCreate(),
    TaskGet(),
    TaskList(),
    TaskUpdate(),
    FunctionTool(web_search),
    FunctionTool(web_fetch),
    FunctionTool(report_progress),
    FunctionTool(plan_task),
    FunctionTool(ask_user),
    *get_compaction_tools(),
    *get_subagent_tools(),
    *get_memory_tools(),
]


async def build_toolkit(config: Config) -> tuple[Toolkit, list[MCPClient]]:
    """Build a Toolkit with all tools and optional MCP clients.

    Args:
        config: Application configuration.

    Returns:
        Tuple of (configured Toolkit, list of connected MCP clients).
    """
    # Read retry configuration for network tool calls
    retry_max = config.tool_retry_max
    retry_backoff = config.tool_retry_backoff
    retry_initial_delay = config.tool_retry_initial_delay
    # Network tools (web_search) already have retry applied via
    # @retry_on_failure in app/search.py with matching defaults.

    # Discover Tool Skills (Python modules with get_tools())
    skill_tools = discover_skills()

    # Combine all tools: built-in + Tool Skills
    all_tools = list(BUILTIN_TOOLS) + skill_tools

    mcps = []
    if config.chrome_mcp_enabled:
        mcp = MCPClient(
            name="chrome-devtools",
            is_stateful=True,
            mcp_config=StdioMCPConfig(
                command="npx",
                args=["-y", "chrome-devtools-mcp@latest"],
            ),
        )
        await mcp.connect()
        mcps.append(mcp)

    # Instruction Skills: load SKILL.md files from skills/ subdirectories
    skill_loader = LocalSkillLoader(directory="skills/", scan_subdir=True)

    toolkit = Toolkit(
        tools=all_tools,
        skills_or_loaders=[skill_loader],
        mcps=mcps if mcps else None,
    )
    return toolkit, mcps