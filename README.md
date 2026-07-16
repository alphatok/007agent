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
┌──────────────────────────────────────────────────────────────────┐
│                        Entry Points                              │
│  ┌──────────┐  ┌─────────────────────────────────────────────┐  │
│  │  CLI     │  │  Agent Service (FastAPI + Web UI)           │  │
│  │  Mode    │  │  POST /chat  │  SSE /stream  │  /api/tasks  │  │
│  └────┬─────┘  └──────────────────┬──────────────────────────┘  │
│       │                            │                              │
│       └──────────┬─────────────────┘                              │
│                  ▼                                                │
│  ┌──────────────────────────────────────┐                        │
│  │         Agent Factory                │  build_agent()          │
│  │  - Model + Credential                │                        │
│  │  - Tools + MCP + Skills + Subagents  │                        │
│  │  - ContextConfig (compaction)        │                        │
│  └──────────────┬───────────────────────┘                        │
│                 ▼                                                 │
│  ┌──────────────────────────────────────┐                        │
│  │           AgentScope                 │  Framework              │
│  │  Agent | Toolkit | Event | Summary   │                        │
│  └──────────────────────────────────────┘                        │
└──────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
AGENTS/
├── main.py                    # Entry: delegates to app.cli
├── pyproject.toml             # uv project config
├── .env                       # API keys
│
├── docs/
│   ├── architecture.md        # Architecture design doc
│   ├── skill-design.md        # Skill system specification
│   └── context-compaction-design.md  # Compaction design
│
├── app/                       # Application layer
│   ├── config.py              # .env → typed Config
│   ├── tools.py               # 13 built-in tools + MCP + skills + subagents
│   ├── search.py              # DuckDuckGo web search tool
│   ├── compaction.py          # context_status tool + compaction config
│   ├── task_manager.py        # Async task CRUD + background execution
│   ├── subagent.py            # Subagent loader, runner, delegate tool
│   ├── agent.py               # build_agent() factory (async)
│   ├── cli.py                 # Interactive CLI loop with compaction detection
│   └── service.py             # FastAPI REST + SSE + Web UI + Task API
│
├── subagents/                 # Subagent configs (AGENT.md format)
│   ├── code-reviewer/         # Code review subagent
│   │   └── AGENT.md
│   └── test-generator/        # Test generation subagent
│       └── AGENT.md
│
├── skills/                    # 双层 Skill 体系
│   ├── __init__.py            # discover_skills() - Tool Skill 发现
│   ├── anthropic_skill.py     # [Tool Skill] Claude API 工具
│   ├── openai_skill.py        # [Tool Skill] GPT API 工具
│   ├── code-review/           # [Instruction Skill] 代码审查
│   │   └── SKILL.md
│   └── test-generation/       # [Instruction Skill] 测试生成
│       └── SKILL.md
│
└── tests/                     # All tests (58 tests)
    ├── test_config.py
    ├── test_tools.py
    ├── test_agent.py
    ├── test_cli.py
    ├── test_service.py
    ├── test_search.py
    ├── test_skills.py
    ├── test_compaction.py
    ├── test_task_api.py
    └── test_subagent.py
```

## Module Design

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `config.py` | Load .env, provide typed `Config` | `python-dotenv` |
| `tools.py` | Build `Toolkit` with built-in + MCP + skills + subagents | `agentscope`, `skills`, `compaction`, `subagent` |
| `search.py` | DuckDuckGo web search tool | `duckduckgo-search` |
| `compaction.py` | `context_status` tool, compaction monitoring | `agentscope` |
| `task_manager.py` | Async task CRUD, background execution, `.trae/tasks/` persistence | `agentscope` |
| `subagent.py` | Subagent loader, runner, `delegate_subagent` tool | `agentscope`, `yaml` |
| `agent.py` | Create `Agent` from config + toolkit (async) | `config`, `tools`, `subagent` |
| `cli.py` | Interactive CLI loop with event streaming + compaction detection | `agent` |
| `service.py` | FastAPI app with REST + SSE + Web UI + Task API | `agent`, `task_manager` |

### Dependency Flow (high cohesion, low coupling)

```
config.py                     (no deps)
    │
    ├──► compaction.py  ◄──── config.py
    ├──► subagent.py    ◄──── config.py
    ├──► task_manager.py
    │
    ▼
tools.py  ◄──────── config.py, skills/, search.py, compaction.py, subagent.py
    │
    ▼
agent.py  ◄──────── config.py, tools.py, subagent.py
    │
    ├──► cli.py      (imports agent)
    └──► service.py  (imports agent, task_manager)
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
| `COMPACTION_TRIGGER_RATIO` | `0.4` | Compaction trigger ratio (40% of 128K) |
| `COMPACTION_WARNING_TOKENS` | `20000` | Token threshold for warning |

## Built-in Tools (13)

| Tool | Type | Description |
|------|------|-------------|
| `Bash` | Core | Execute shell commands |
| `Read` | Core | Read file contents |
| `Write` | Core | Create / overwrite files |
| `Edit` | Core | Exact string replacement in files |
| `Glob` | Core | File pattern matching |
| `Grep` | Core | Content search (ripgrep) |
| `TaskCreate` | Core | Create a task |
| `TaskGet` | Core | Get task details |
| `TaskList` | Core | List all tasks |
| `TaskUpdate` | Core | Update task status |
| `web_search` | Extension | Search the web via DuckDuckGo |
| `context_status` | Extension | Check context token usage / compaction |
| `delegate_subagent` | Extension | Delegate task to a specialized subagent |

## Context Compaction

AgentScope 内置的 `compress_context()` 自动在每次 reasoning 前检测 token 使用量，超过阈值时生成结构化摘要并替换旧对话历史。

| 级别 | 阈值 | 行为 |
|------|------|------|
| Normal | < 20K tokens | 正常运行 |
| Warning | 20K - 51.2K | `context_status` 工具显示警告 |
| Auto-Compact | > 51.2K (40% of 128K) | 自动触发压缩 |

压缩保留：任务概述、当前状态、重要发现、下一步、用户偏好。丢弃：完整工具输出、中间推理、精确代码。

```
  [Compaction] Context compressed, summary updated
```

## Skill System

采用**双层 Skill 体系**，遵循 AgentScope 原生 Skill 协议：

### Layer 1: Tool Skill（工具型技能）

Python 模块通过 `get_tools()` 导出 `FunctionTool`，为 Agent 提供新的工具能力。

| Skill | Tools | Requires |
|-------|-------|----------|
| `anthropic_skill` | `anthropic_chat` — Send messages to Claude | `ANTHROPIC_API_KEY` |
| `openai_skill` | `openai_chat` — Send messages to GPT | `OPENAI_API_KEY` |

### Layer 2: Instruction Skill（指令型技能）

`SKILL.md` 文件（YAML frontmatter + Markdown 指令），教 Agent 如何用已有工具完成特定任务。Agent 通过内置 `Skill` 工具读取。

| Skill | 描述 |
|-------|------|
| `code-review` | 系统性代码审查：检查质量、安全、性能、可维护性 |
| `test-generation` | 生成高质量 pytest 单元测试，遵循 AAA 模式 |

### 工作流程

```
1. 启动时 → LocalSkillLoader 扫描 SKILL.md → 解析 frontmatter
2. 对话时 → 系统提示词注入 Skill 列表（name + description）
3. Agent 判断需要 → 调用 Skill("code-review") 工具
4. 返回 SKILL.md 完整指令 → Agent 按指令执行
```

### 添加新 Skill

**Tool Skill:**
1. 创建 `skills/your_skill.py`
2. 定义 `get_tools() -> list[FunctionTool]`
3. 重启，自动发现

**Instruction Skill:**
1. 创建 `skills/your-skill/SKILL.md`
2. 编写 YAML frontmatter + Markdown 指令（≤500行）
3. 重启，自动加载

## Subagent System

参考 Anthropic Claude Code 的 Subagent 机制，支持将任务委派给独立的专用 Agent 实例。

### 架构

```
subagents/name/AGENT.md   →  SubagentLoader  →  SubagentConfig
                                                     ↓
delegate_subagent("name") →  SubagentRunner  →  独立 Agent 实例
  (FunctionTool)                                   - 白名单工具
                                                   - 独立上下文
                                                   - 无 MCP/Skills
```

### 可用 Subagents

| Subagent | 描述 | 工具白名单 |
|----------|------|-----------|
| `code-reviewer` | 代码审查：质量、安全、性能、可维护性 | Read, Grep, Glob, Bash |
| `test-generator` | 生成 pytest 单元测试，AAA 模式 | Read, Grep, Glob, Bash, Write |

### Adding a Subagent

1. 创建 `subagents/name/AGENT.md`
2. 编写 YAML frontmatter（name, description, tools, model）
3. 编写 Markdown 系统提示词
4. 重启，Agent 自动发现

## Async Task API

通过 HTTP 提交异步任务，轮询状态获取结果。任务存储在 `.trae/tasks/`。

### Endpoints

```
POST   /api/tasks            → {"task_id":"...", "status":"pending"}
GET    /api/tasks/{task_id}  → {"status":"running", "result":null}
GET    /api/tasks             → [tasks...]
DELETE /api/tasks/{task_id}  → {"task_id":"...", "status":"cancelled"}
```

### 状态机

```
pending → running → completed
                  → failed
         → cancelled
```

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
| Tests | `uv run pytest tests/ -v` | 58 unit tests |

### Service API

```
GET  /health              → {"status": "ok", "agent": "AgentScope"}
POST /chat                → {"content": "..."} → {"reply": "..."}
GET  /chat/stream?q=...   → SSE streaming response
GET  /api/files/list      → List workspace files
GET  /api/files/download  → Download a file
POST /api/tasks           → Submit async task
GET  /api/tasks/{id}      → Query task status
GET  /api/tasks           → List all tasks
DELETE /api/tasks/{id}    → Cancel task
```

## Extension Points

1. **New Tool** → Add to `app/tools.py` `BUILTIN_TOOLS` list
2. **New Skill** → Create `.py` in `skills/` or `SKILL.md` in `skills/*/`
3. **New Subagent** → Create `subagents/name/AGENT.md`
4. **New MCP** → Add to `app/tools.py` `build_toolkit()`
5. **New Model** → Update `app/config.py` + `app/agent.py`
6. **New Entry Mode** → Create `app/new_mode.py`, import `build_agent()`

## Dependencies

- Python >= 3.12
- Node.js >= 20 (for Chrome DevTools MCP)
- [AgentScope 2.0](https://github.com/agentscope-ai/agentscope)
- [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/) (for service mode)
- [OpenAI Python SDK](https://github.com/openai/openai-python) (for OpenAI skill)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) (for Anthropic skill)
- [DuckDuckGo Search](https://github.com/deedy5/duckduckgo_search) (for web search)
- [PyYAML](https://pyyaml.org/) (for Subagent AGENT.md parsing)