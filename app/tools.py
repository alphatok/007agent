"""Tool registration module.

Provides all built-in tools and optional Chrome DevTools MCP integration.
"""
from agentscope.mcp import MCPClient
from agentscope.mcp._config import StdioMCPConfig
from agentscope.tool import (
    Bash,
    Edit,
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
]


async def build_toolkit(config: Config) -> Toolkit:
    """Build a Toolkit with all built-in tools and optional MCP clients.

    Args:
        config: Application configuration.

    Returns:
        Configured Toolkit instance ready for agent use.
    """
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
        tools=BUILTIN_TOOLS,
        mcps=mcps if mcps else None,
    )