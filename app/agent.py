"""Agent factory module.

Creates a fully configured Agent instance from config and toolkit.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from agentscope.agent import Agent
from agentscope.agent._config import ContextConfig
from agentscope.credential import DeepSeekCredential
from agentscope.model import DeepSeekChatModel
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.state import AgentState
from agentscope.tool import Toolkit

from app.config import Config
from app.subagent import SubagentLoader, SubagentRunner, set_subagent_runner

if TYPE_CHECKING:
    from app.store import SessionStore
    from app.memory import MemoryStore

SYSTEM_PROMPT = (
    "You are a helpful AI assistant powered by DeepSeek V4 Pro. "
    "You have access to a wide range of tools including file operations, "
    "shell commands, code search, task management, web search, and Chrome "
    "browser control via Chrome DevTools. "
    "Use these tools effectively to help the user accomplish their goals. "
    "Always use the web_search tool to search the internet for real-time information, current events, weather, news, and any facts you are not certain about. Do not guess or refuse to answer — search first. "
    "When working on complex tasks, use the task management tools "
    "(TaskCreate, TaskGet, TaskList, TaskUpdate) to plan and track "
    "your progress. "
    "You also have access to Skills - specialized instructions for "
    "specific tasks like code review and test generation. "
    "When a task matches a skill's description, use the Skill tool to "
    "read the full instructions and follow them precisely."
    "\n\n"
    "## Long-Running Task Guidelines\n"
    "When working on complex, multi-step tasks:\n"
    "1. Use plan_task to break down the task into subtasks before starting\n"
    "2. Execute each subtask in order\n"
    "3. Call report_progress after each subtask completes\n"
    "4. Use ask_user ONLY for critical decisions during complex tasks - "
    "never for simple conversation, greetings, or clarifications"
    "\n\n"
    "## Memory Management (CRITICAL)\n"
    "You have a persistent cross-session memory system that survives "
    "session switches. This is how you remember the user across different "
    "conversations.\n\n"
    "**MANDATORY: search memory BEFORE answering** when the user asks:\n"
    "- 'Who am I?' / '你知道我是谁吗' / 'Do you remember me?'\n"
    "- 'What do you know about me?' / '你还记得什么关于我的事'\n"
    "- 'What are my preferences?' / '我的偏好是什么'\n"
    "- Any question about past conversations or personal facts\n"
    "- **Do NOT answer with 'I don't know' or 'I don't remember' without "
    "first calling search_memory(query='user name identity', scope='global')**\n\n"
    "**When the user tells you to remember something**:\n"
    "- 'Remember my name is XXX' / '记住我叫XXX' → add_memory with "
    "type='semantic', scope='global'\n"
    "- 'I prefer using uv for Python' → add_memory with type='semantic', "
    "scope='global'\n"
    "- Important events → add_memory with type='episodic', scope='global'\n"
    "- Workflows/instructions → add_memory with type='procedural', "
    "scope='global'\n\n"
    "**Memory scope**:\n"
    "- scope='global': persists across ALL sessions (default, use for "
    "user identity, preferences, permanent facts)\n"
    "- scope='session': only usable in the current session (use for "
    "temporary context)\n\n"
    "**Other memory operations**:\n"
    "- update_memory: modify existing memories (use instead of creating duplicates)\n"
    "- list_memories: review what you already know (scope='global' to see permanent facts)\n"
    "- forget_memory: remove outdated or incorrect memories"
)


async def build_agent(config: Config, toolkit: Toolkit,
                      store: "SessionStore | None" = None,
                      memory: "MemoryStore | None" = None) -> Agent:
    """Build a fully configured Agent instance.

    Args:
        config: Application configuration with API keys and settings.
        toolkit: Configured Toolkit with tools, skills, and MCP clients.
        store: Optional SessionStore for session persistence.
        memory: Optional MemoryStore for cross-session memory.

    Returns:
        An Agent instance ready for use.
    """
    permission_mode = PermissionMode(config.permission_mode)

    # Initialize Subagent system for delegate_subagent tool
    loader = SubagentLoader()
    runner = SubagentRunner(config, loader)
    set_subagent_runner(runner)

    # Inject skill instructions into system prompt
    skill_instructions = await toolkit.get_skill_instructions()
    system_prompt = SYSTEM_PROMPT
    if skill_instructions:
        system_prompt = SYSTEM_PROMPT + "\n\n" + skill_instructions

    agent = Agent(
        name="AgentScope",
        system_prompt=system_prompt,
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
        context_config=ContextConfig(
            trigger_ratio=config.compaction_trigger_ratio,
        ),
    )

    # Inject store and memory for access by CLI/Service
    object.__setattr__(agent, "_store", store)
    object.__setattr__(agent, "_memory", memory)

    return agent