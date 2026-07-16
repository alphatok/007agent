"""Tool registration module.

Provides all built-in tools, search capability, skill system, and optional
Chrome DevTools MCP integration.

Skill system has two layers:
  - Tool Skills: Python modules in skills/ with get_tools() (auto-discovered)
  - Instruction Skills: SKILL.md files in skills/*/ (loaded via LocalSkillLoader)
"""
from agentscope.mcp import MCPClient
from agentscope.mcp._config import StdioMCPConfig
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
    Write,
)

from app.compaction import get_tools as get_compaction_tools
from app.config import Config
from app.search import web_search
from app.subagent import get_tools as get_subagent_tools
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
    *get_compaction_tools(),
    *get_subagent_tools(),
]


async def build_toolkit(config: Config) -> Toolkit:
    """Build a Toolkit with all tools and optional MCP clients.

    Args:
        config: Application configuration.

    Returns:
        Configured Toolkit instance ready for agent use.
    """
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

    return Toolkit(
        tools=all_tools,
        skills_or_loaders=[skill_loader],
        mcps=mcps if mcps else None,
    )