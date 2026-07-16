"""Subagent orchestration module.

Provides Subagent configuration loading, independent Agent instance creation,
and a ``delegate_subagent`` FunctionTool for the main Agent to delegate tasks.

Subagent configs follow Anthropic's AGENT.md format (YAML frontmatter +
Markdown system prompt), stored in the ``subagents/`` directory.

Architecture:
  SubagentLoader  →  loads AGENT.md files
  SubagentRunner  →  creates Agent with whitelisted tools, runs tasks
  delegate_subagent() → FunctionTool exposed to main Agent
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator

from agentscope.message import TextBlock, ToolResultState, UserMsg
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.state import AgentState
from agentscope.tool import (
    Bash,
    Edit,
    FunctionTool,
    Glob,
    Grep,
    Read,
    Toolkit,
    ToolChunk,
    Write,
)

if TYPE_CHECKING:
    from agentscope.agent import Agent

    from app.config import Config

SUBAgENTS_DIR = Path("subagents")

# Tool name → class mapping for whitelisted tools
_TOOL_REGISTRY: dict[str, type] = {
    "Read": Read,
    "Grep": Grep,
    "Glob": Glob,
    "Bash": Bash,
    "Write": Write,
    "Edit": Edit,
}


@dataclass
class SubagentConfig:
    """Parsed Subagent configuration from AGENT.md."""

    name: str
    description: str
    tools: list[str]
    model: str
    system_prompt: str


class SubagentLoader:
    """Load Subagent configurations from ``subagents/`` directory.

    Each subagent is a directory containing an ``AGENT.md`` file with
    YAML frontmatter and Markdown body.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or SUBAgENTS_DIR

    def load(self, name: str) -> SubagentConfig | None:
        """Load a single Subagent config by name.

        Args:
            name: Subagent name (directory name).

        Returns:
            SubagentConfig if found, None otherwise.
        """
        path = self.base_dir / name / "AGENT.md"
        if not path.exists():
            return None
        return self._parse(path)

    def list_all(self) -> dict[str, SubagentConfig]:
        """List all available Subagent configs.

        Returns:
            Dict mapping name → SubagentConfig.
        """
        configs: dict[str, SubagentConfig] = {}
        if not self.base_dir.exists():
            return configs
        for subdir in sorted(self.base_dir.iterdir()):
            if subdir.is_dir():
                config = self.load(subdir.name)
                if config:
                    configs[subdir.name] = config
        return configs

    def _parse(self, path: Path) -> SubagentConfig | None:
        """Parse an AGENT.md file using YAML frontmatter."""
        import yaml

        text = path.read_text(encoding="utf-8")
        # Extract YAML frontmatter between --- markers
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not match:
            return None
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return None
        body = match.group(2).strip()

        tools_raw = meta.get("tools", "")
        if isinstance(tools_raw, str):
            tools = [t.strip() for t in tools_raw.split(",") if t.strip()]
        else:
            tools = list(tools_raw) if tools_raw else []

        return SubagentConfig(
            name=meta.get("name", path.parent.name),
            description=meta.get("description", ""),
            tools=tools,
            model=meta.get("model", "deepseek-v4-pro"),
            system_prompt=body,
        )


class SubagentRunner:
    """Create and run independent Subagent instances.

    Each Subagent gets:
    - A new AgentState with independent context
    - A whitelisted Toolkit (only tools declared in AGENT.md)
    - No MCP, no Skills (clean context)
    - The Subagent's own system prompt
    """

    def __init__(self, config: "Config", loader: SubagentLoader) -> None:
        self._config = config
        self._loader = loader

    async def run(
        self,
        subagent_name: str,
        task: str,
        context: str | None = None,
    ) -> str:
        """Create a Subagent and execute a task.

        Args:
            subagent_name: Name of the Subagent to invoke.
            task: The task description to send to the Subagent.
            context: Optional additional context.

        Returns:
            The Subagent's reply text.

        Raises:
            ValueError: If Subagent not found or has invalid tools.
        """
        from agentscope.agent import Agent
        from agentscope.credential import DeepSeekCredential
        from agentscope.model import DeepSeekChatModel

        subagent_config = self._loader.load(subagent_name)
        if not subagent_config:
            raise ValueError(
                f"Subagent '{subagent_name}' not found. "
                f"Available: {list(self._loader.list_all().keys())}",
            )

        # Build whitelisted toolkit
        tools = []
        for tool_name in subagent_config.tools:
            tool_cls = _TOOL_REGISTRY.get(tool_name)
            if tool_cls is None:
                raise ValueError(
                    f"Unknown tool '{tool_name}' in Subagent "
                    f"'{subagent_name}'. Available: "
                    f"{list(_TOOL_REGISTRY.keys())}",
                )
            tools.append(tool_cls())

        toolkit = Toolkit(tools=tools)

        # Build system prompt with optional context
        system_prompt = subagent_config.system_prompt
        if context:
            system_prompt += f"\n\n## Additional Context\n{context}"

        # Create independent Agent
        agent = Agent(
            name=f"Subagent:{subagent_name}",
            system_prompt=system_prompt,
            model=DeepSeekChatModel(
                credential=DeepSeekCredential(
                    api_key=self._config.deepseek_api_key,
                    base_url=self._config.deepseek_base_url,
                ),
                model=subagent_config.model,
                stream=False,
            ),
            toolkit=toolkit,
            state=AgentState(
                permission_context=PermissionContext(
                    mode=PermissionMode.BYPASS,
                ),
            ),
        )

        prompt = task
        if context:
            prompt = f"{task}\n\nContext: {context}"

        reply = await agent.reply(UserMsg("user", prompt))
        return str(reply)


# Module-level state for delegate_subagent closure injection
_runner: SubagentRunner | None = None


def set_subagent_runner(runner: SubagentRunner) -> None:
    """Set the global SubagentRunner for delegate_subagent tool."""
    global _runner
    _runner = runner


async def delegate_subagent(
    subagent_name: str,
    task: str,
    context: str | None = None,
) -> AsyncGenerator[ToolChunk, None]:
    """Delegate a task to a specialized subagent.

    The subagent runs in its own independent context with only the tools
    declared in its AGENT.md configuration. Results are returned to the
    main agent without intermediate tool outputs.

    Args:
        subagent_name: Name of the subagent to invoke
            (e.g., "code-reviewer", "test-generator").
        task: The specific task for the subagent to complete.
        context: Optional additional context to pass to the subagent.
    """
    if _runner is None:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    text="Subagent system not initialized. "
                    "SubagentRunner must be set before use.",
                ),
            ],
        )
        return

    try:
        result = await _runner.run(
            subagent_name=subagent_name,
            task=task,
            context=context,
        )
        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[
                TextBlock(
                    text=f"[Subagent: {subagent_name}]\n{result}",
                ),
            ],
        )
    except ValueError as e:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[TextBlock(text=str(e))],
        )
    except Exception as e:
        yield ToolChunk(
            state=ToolResultState.ERROR,
            content=[
                TextBlock(
                    text=f"Subagent '{subagent_name}' failed: {e}",
                ),
            ],
        )


def get_tools() -> list[FunctionTool]:
    """Return the Subagent delegation tool."""
    return [FunctionTool(delegate_subagent)]