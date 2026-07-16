"""Tool registration module.

Provides all built-in tools, search capability, skill system, and optional
Chrome DevTools MCP integration.
"""
from agentscope.mcp import MCPClient
from agentscope.mcp._config import StdioMCPConfig
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
    Write,
)

from app.config import Config
from app.search import web_search
from skills import discover_skills

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
]


async def build_toolkit(config: Config) -> Toolkit:
    """Build a Toolkit with all tools and optional MCP clients.

    Args:
        config: Application configuration.

    Returns:
        Configured Toolkit instance ready for agent use.
    """
    # Discover skill tools
    skill_tools = discover_skills()

    # Combine all tools: built-in + skills
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

    return Toolkit(
        tools=all_tools,
        mcps=mcps if mcps else None,
    )