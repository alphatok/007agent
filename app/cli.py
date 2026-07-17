"""CLI entry point.

Interactive terminal-based agent loop with full tool execution visibility.
"""
import asyncio
import os

from agentscope.agent import Agent
from agentscope.event import EventType
from agentscope.message import ToolResultState, UserMsg

BANNER = """\
============================================================
AgentScope Agent powered by DeepSeek V4 Pro
Built-in tools: Bash, Read, Write, Edit, Glob, Grep,
                TaskCreate, TaskGet, TaskList, TaskUpdate
MCP tools:      Chrome DevTools (chrome-devtools-mcp)
Type 'exit' or 'quit' to stop.
============================================================"""


async def run_cli(agent: Agent) -> None:
    """Run the interactive CLI agent loop.

    Args:
        agent: Configured Agent instance.
    """
    print(BANNER)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        print()
        await _stream_reply(agent, user_input)


async def _stream_reply(agent: Agent, user_input: str) -> None:
    """Stream agent reply with tool execution visibility.

    Args:
        agent: The Agent instance.
        user_input: User's text input.
    """
    tool_names: dict[str, str] = {}
    tool_result_lines: dict[str, int] = {}
    _last_summary: str | None = agent.state.summary

    async for evt in agent.reply_stream(UserMsg("user", user_input)):
        # Detect context compaction
        current_summary = agent.state.summary
        if current_summary != _last_summary:
            _last_summary = current_summary
            if current_summary:
                print(
                    "\n  [Compaction] Context compressed, summary updated",
                    flush=True,
                )

        match evt.type:
            case EventType.REPLY_START:
                print("Agent: ", end="", flush=True)
            case EventType.TEXT_BLOCK_DELTA:
                if evt.delta:
                    print(evt.delta, end="", flush=True)
            case EventType.REPLY_END:
                print()
            case EventType.TOOL_CALL_START:
                tool_names[evt.tool_call_id] = evt.tool_call_name
                print(f"\n  [Tool] {evt.tool_call_name}", flush=True)
            case EventType.TOOL_RESULT_START:
                name = tool_names.get(evt.tool_call_id, evt.tool_call_name)
                print(f"  [....] {name} running...", flush=True)
            case EventType.TOOL_RESULT_TEXT_DELTA:
                if evt.delta:
                    tid = evt.tool_call_id
                    count = tool_result_lines.get(tid, 0)
                    if count < 5:
                        lines = evt.delta.strip().split("\n")
                        for line in lines[: 5 - count]:
                            if line.strip():
                                print(
                                    f"  [ .. ] {line.strip()[:100]}",
                                    flush=True,
                                )
                        tool_result_lines[tid] = count + len(lines)
                    elif count == 5:
                        print(
                            "  [ .. ] ... (output truncated)",
                            flush=True,
                        )
                        tool_result_lines[tid] = 6
            case EventType.TOOL_RESULT_END:
                name = tool_names.get(evt.tool_call_id, "unknown")
                match evt.state:
                    case ToolResultState.SUCCESS:
                        print(f"  [ OK ] {name} succeeded", flush=True)
                    case ToolResultState.ERROR:
                        print(f"  [FAIL] {name} failed", flush=True)
                    case ToolResultState.INTERRUPTED:
                        print(f"  [STOP] {name} interrupted", flush=True)
                    case ToolResultState.DENIED:
                        print(f"  [DENY] {name} denied", flush=True)
                    case _:
                        print(
                            f"  [ ?? ] {name} {evt.state.value}",
                            flush=True,
                        )
            case _:
                pass


def main() -> None:
    """CLI entry point."""
    from app.agent import build_agent
    from app.config import load_config
    from app.memory import MemoryStore
    from app.memory_tool import set_memory_store, set_retriever
    from app.retriever import HybridRetriever
    from app.store import SessionStore
    from app.tools import build_toolkit

    async def _run() -> None:
        config = load_config()

        # Initialize persistence
        os.makedirs(config.data_dir, exist_ok=True)
        store = SessionStore(config.db_path)
        memory = MemoryStore(config.db_path, config.zvec_path)
        retriever = HybridRetriever(
            config.db_path, config.zvec_path, memory,
        )
        set_memory_store(memory)
        set_retriever(retriever)

        toolkit = await build_toolkit(config)
        agent = await build_agent(config, toolkit, store=store, memory=memory)

        # Session management
        if config.persistence_mode != "none":
            sessions = store.list_sessions(limit=10)
            if sessions:
                print("\nRecent sessions:")
                for i, s in enumerate(sessions):
                    print(f"  [{i}] {s['name']} "
                          f"({s['message_count']} msgs, "
                          f"{s['updated_at'][:19]})")
                print("  [n] New session")
                choice = input("Select session (default=n): ").strip()
                if choice and choice.isdigit():
                    idx = int(choice)
                    if 0 <= idx < len(sessions):
                        store.load_session(sessions[idx]["id"], agent)
                        print(f"Resumed session: {sessions[idx]['name']}")
                else:
                    store.create_session()
            else:
                store.create_session(name="CLI Session")

        await run_cli(agent)

        # Cleanup on exit
        if config.persistence_mode != "none":
            store.cleanup_old_sessions(
                config.session_max_count, config.session_max_age_days,
            )
            if config.memory_enabled:
                memory.decay(
                    max_age_days=config.memory_decay_days,
                )

    asyncio.run(_run())


if __name__ == "__main__":
    main()