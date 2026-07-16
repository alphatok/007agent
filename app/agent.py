"""Agent factory module.

Creates a fully configured Agent instance from config and toolkit.
"""
from agentscope.agent import Agent
from agentscope.credential import DeepSeekCredential
from agentscope.model import DeepSeekChatModel
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.state import AgentState
from agentscope.tool import Toolkit

from app.config import Config

SYSTEM_PROMPT = (
    "You are a helpful AI assistant powered by DeepSeek V4 Pro. "
    "You have access to a wide range of tools including file operations, "
    "shell commands, code search, task management, and Chrome browser "
    "control via Chrome DevTools. "
    "Use these tools effectively to help the user accomplish their goals. "
    "When working on complex tasks, use the task management tools "
    "(TaskCreate, TaskGet, TaskList, TaskUpdate) to plan and track "
    "your progress. "
    "Use Chrome DevTools tools to navigate web pages, take screenshots, "
    "debug performance issues, and automate browser interactions."
)


def build_agent(config: Config, toolkit: Toolkit) -> Agent:
    """Build a fully configured Agent instance.

    Args:
        config: Application configuration with API keys and settings.
        toolkit: Configured Toolkit with tools and MCP clients.

    Returns:
        An Agent instance ready for use.
    """
    permission_mode = PermissionMode(config.permission_mode)

    return Agent(
        name="AgentScope",
        system_prompt=SYSTEM_PROMPT,
        model=DeepSeekChatModel(
            credential=DeepSeekCredential(
                api_key=config.deepseek_api_key,
                base_url=config.deepseek_base_url,
            ),
            model=config.deepseek_model,
            stream=True,
        ),
        toolkit=toolkit,
        state=AgentState(
            permission_context=PermissionContext(mode=permission_mode),
        ),
    )