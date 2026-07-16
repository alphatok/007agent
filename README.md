# AgentScope Agent

AI Agent powered by [DeepSeek V4 Pro](https://api.deepseek.com) + [AgentScope 2.0](https://github.com/agentscope-ai/agentscope), supporting CLI and Web UI (Studio) modes.

## Quick Start

```bash
# 1. Set your API keys
cp .env.example .env   # edit .env with your API keys

# 2. Run
uv run main.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Entry Points                        │
│  ┌──────────┐  ┌──────────────────────────────────────┐ │
│  │  CLI     │  │  Agent Service (FastAPI + Web UI)    │ │
│  │  Mode    │  │  POST /chat  │  SSE /stream          │ │
│  └────┬─────┘  └──────────────────┬───────────────────┘ │
│       │                            │                     │
│       └──────────┬─────────────────┘                     │
│                  ▼                                       │
│  ┌──────────────────────────────┐                        │
│  │       Agent Factory          │  build_agent()         │
│  │  - Model + Credential        │                        │
│  │  - Tools + MCP               │                        │
│  └──────────────┬───────────────┘                        │
│                 ▼                                        │
│  ┌──────────────────────────────┐                        │
│  │         AgentScope           │  Framework             │
│  │  Agent | Toolkit | Event     │                        │
│  └──────────────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```
AGENTS/
├── main.py                    # Entry: delegates to app.cli
├── pyproject.toml             # uv project config
├── .env                       # API keys
│
├── docs/
│   └── architecture.md        # Detailed architecture doc
│
├── app/                       # Application layer
│   ├── config.py              # .env → typed Config
│   ├── tools.py               # 11 built-in + Chrome MCP + skills
│   ├── search.py              # DuckDuckGo web search tool
│   ├── agent.py               # build_agent() factory
│   ├── cli.py                 # Interactive CLI loop
│   └── service.py             # FastAPI REST + SSE + Web UI
│
├── skills/                    # Skill system (auto-discovered)
│   ├── __init__.py            # discover_skills() loader
│   ├── anthropic_skill.py     # Anthropic Claude API tools
│   └── openai_skill.py        # OpenAI GPT API tools
│
└── tests/                     # All tests
    ├── test_config.py
    ├── test_tools.py
    ├── test_agent.py
    ├── test_cli.py
    ├── test_service.py
    ├── test_search.py
    └── test_skills.py
```

## Module Design

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `config.py` | Load .env, provide typed `Config` | `python-dotenv` |
| `tools.py` | Build `Toolkit` with built-in + MCP + skills | `agentscope`, `skills` |
| `search.py` | DuckDuckGo web search tool | `duckduckgo-search` |
| `agent.py` | Create `Agent` from config + toolkit | `config`, `tools` |
| `cli.py` | Interactive CLI loop with event streaming | `agent` |
| `service.py` | FastAPI app with REST + SSE + Web UI | `agent` |

### Dependency Flow (high cohesion, low coupling)

```
config.py           (no deps)
    │
    ▼
tools.py  ◄──────── config.py, skills/, search.py
    │
    ▼
agent.py  ◄──────── config.py, tools.py
    │
    ├──► cli.py      (imports agent)
    └──► service.py  (imports agent)
```

## Configuration

All settings via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | *(required)* | DeepSeek API key |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | Model name |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API base URL |
| `ANTHROPIC_API_KEY` | *(optional)* | Anthropic API key for Claude skill |
| `OPENAI_API_KEY` | *(optional)* | OpenAI API key for GPT skill |
| `PERMISSION_MODE` | `bypass` | bypass / ask / deny |
| `CHROME_MCP_ENABLED` | `true` | Enable Chrome DevTools MCP |

## Built-in Tools (11)

| Tool | Description |
|------|-------------|
| `Bash` | Execute shell commands |
| `Read` | Read file contents |
| `Write` | Create / overwrite files |
| `Edit` | Exact string replacement in files |
| `Glob` | File pattern matching |
| `Grep` | Content search (ripgrep) |
| `TaskCreate` | Create a task |
| `TaskGet` | Get task details |
| `TaskList` | List all tasks |
| `TaskUpdate` | Update task status |
| `web_search` | Search the web via DuckDuckGo |

## Skill System

Skills are auto-discovered Python modules in the `skills/` directory. Each skill exports a `get_tools()` function returning a list of `FunctionTool` instances.

### Available Skills

| Skill | Tools | Requires |
|-------|-------|----------|
| `anthropic_skill` | `anthropic_chat` — Send messages to Claude | `ANTHROPIC_API_KEY` |
| `openai_skill` | `openai_chat` — Send messages to GPT | `OPENAI_API_KEY` |

### Adding a New Skill

1. Create a new `.py` file in `skills/`
2. Define a `get_tools() -> list[FunctionTool]` function
3. Each tool is an async generator yielding `ToolChunk` with `[TextBlock(text=...)]` content
4. Restart — the skill is auto-discovered on startup

## MCP Integration

[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) for browser control:

- Navigate pages, take screenshots
- Performance traces and debugging
- Network request inspection
- DOM manipulation and automation

## Tool Execution Visibility

All tool calls show real-time status in console:

```
  [Tool] Bash
  [....] Bash running...
  [ .. ] /Users/bruceyang/AGENTS
  [ OK ] Bash succeeded
```

| Icon | Meaning |
|------|---------|
| `[Tool]` | Tool invoked |
| `[....]` | Tool running |
| `[ .. ]` | Output data (first 5 lines) |
| `[ OK ]` | Success |
| `[FAIL]` | Failed |
| `[STOP]` | Interrupted |
| `[DENY]` | Denied |

## Entry Points

| Mode | Command | Description |
|------|---------|-------------|
| CLI | `uv run main.py` | Interactive terminal |
| Service | `uv run python -m app.service` | HTTP API on :8000 |
| Tests | `uv run pytest tests/ -v` | All unit tests |

### Service API

```
GET  /health              → {"status": "ok", "agent": "AgentScope"}
POST /chat                → {"content": "..."} → {"reply": "..."}
GET  /chat/stream?q=...   → SSE streaming response
GET  /api/files/list      → List workspace files
GET  /api/files/download  → Download a file
```

## Extension Points

1. **New Tool** → Add to `app/tools.py` `BUILTIN_TOOLS` list
2. **New Skill** → Create `.py` file in `skills/` with `get_tools()`
3. **New MCP** → Add to `app/tools.py` `build_toolkit()`
4. **New Model** → Update `app/config.py` + `app/agent.py`
5. **New Entry Mode** → Create `app/new_mode.py`, import `build_agent()`

## Dependencies

- Python >= 3.12
- Node.js >= 20 (for Chrome DevTools MCP)
- [AgentScope 2.0](https://github.com/agentscope-ai/agentscope)
- [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/) (for service mode)
- [OpenAI Python SDK](https://github.com/openai/openai-python) (for OpenAI skill)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) (for Anthropic skill)
- [DuckDuckGo Search](https://github.com/deedy5/duckduckgo_search) (for web search)