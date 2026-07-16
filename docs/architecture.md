# AgentScope Agent - Architecture Design

## 1. Overview

An AI Agent application powered by DeepSeek V4 Pro, supporting both CLI and
Web UI (AgentScope Studio) interaction modes with a shared agent core.

Features:
- 13 built-in tools + Chrome DevTools MCP
- Web search via DuckDuckGo
- Dual-layer Skill system (Tool + Instruction)
- Context compaction (auto-triggered at 40% of context window)
- Subagent delegation (Claude Code-style AGENT.md configs)
- Async task HTTP API (submit → poll status)

## 2. Architecture

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

## 3. Module Design

```
app/
├── __init__.py
├── config.py          # Config: load .env, typed settings
├── tools.py           # Tools:  register all built-in + MCP + skills + subagents
├── search.py          # Search: DuckDuckGo web search tool
├── compaction.py      # Compaction: context_status tool + monitoring
├── task_manager.py    # Tasks: async task CRUD + background execution
├── subagent.py        # Subagent: loader, runner, delegate_subagent tool
├── agent.py           # Agent:  build_agent() factory (async)
├── cli.py             # CLI:    interactive terminal loop + compaction detection
└── service.py         # Service: FastAPI REST + SSE + Web UI + Task API

subagents/             # Subagent configs (AGENT.md format)
├── code-reviewer/
│   └── AGENT.md
└── test-generator/
    └── AGENT.md

skills/                # Skill system (双层体系)
├── __init__.py        # discover_skills() - Tool Skill 发现
├── anthropic_skill.py # [Tool Skill] Anthropic Claude API 工具
├── openai_skill.py    # [Tool Skill] OpenAI GPT API 工具
├── code-review/       # [Instruction Skill] 代码审查
│   └── SKILL.md
└── test-generation/   # [Instruction Skill] 测试生成
    └── SKILL.md
```

### 3.1 Module Responsibilities

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `config.py` | Load .env, provide typed config | `python-dotenv` |
| `tools.py` | Build Toolkit with built-in + MCP + skills + subagents | `agentscope`, `skills`, `compaction`, `subagent` |
| `search.py` | DuckDuckGo web search tool | `duckduckgo-search` |
| `compaction.py` | `context_status` tool, compaction monitoring | `agentscope` |
| `task_manager.py` | Async task CRUD, background execution, `.trae/tasks/` persistence | `asyncio`, `json` |
| `subagent.py` | Subagent loader, runner, `delegate_subagent` tool | `agentscope`, `yaml` |
| `agent.py` | Create Agent from config + toolkit (async, with ContextConfig) | `config`, `tools`, `subagent` |
| `cli.py` | Interactive CLI loop with event streaming + compaction detection | `agent` |
| `service.py` | FastAPI app with REST + SSE + Web UI + Task API | `agent`, `task_manager` |

### 3.2 Dependency Flow

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

### 3.3 Design Principles

- **High Cohesion**: Each module has one clear responsibility
- **Low Coupling**: Modules depend only on what they need, via interfaces
- **Extensible**: Add new tools in `tools.py`, new skills in `skills/`, new subagents in `subagents/`, new modes as new entry points
- **Not Over-Engineered**: No abstract base classes without need

### 3.4 Skill System

采用**双层 Skill 体系**，兼顾 AgentScope 原生 Skill 协议和项目扩展需求：

**Layer 1: Tool Skill（工具型技能）**
- Python 模块，导出 `get_tools() -> list[FunctionTool]`
- 为 Agent 提供新的工具能力（如调用 Anthropic/OpenAI API）
- 通过 `discover_skills()` 自动发现，注册到 `Toolkit.tools`

**Layer 2: Instruction Skill（指令型技能）**
- 目录 + SKILL.md 文件，含 YAML frontmatter + Markdown 指令
- 教 Agent 如何使用已有工具完成特定领域任务
- 通过 `LocalSkillLoader` 加载，Agent 通过 `Skill` 工具读取
- 遵循 AgentScope 原生 Skill 协议

**最佳实践:**
- SKILL.md 主体 ≤500 行，简洁至上
- Frontmatter: name（1-64字符小写+连字符），description（第三人称，含触发词+反向触发词）
- 分步骤编号，第三人称祈使语气
- 渐进式披露：主文件导航，细节放 references/
- 一级引用深度，正斜杠路径

### 3.5 Subagent System

参考 Anthropic Claude Code 的 Subagent 机制，支持将任务委派给独立的专用 Agent 实例。

**配置格式**（`subagents/name/AGENT.md`）：
```yaml
---
name: code-reviewer
description: 审查代码变更，检查代码质量、安全性...
tools: Read, Grep, Glob, Bash
model: deepseek-v4-pro
---
（Markdown 系统提示词）
```

**关键设计**：
- 独立上下文：每个 Subagent 使用新的 AgentState
- 工具白名单：只授予 AGENT.md 中声明的工具
- 无 MCP/Skills：保持上下文干净
- 结果回传：只返回最终结果，不返回中间过程

**架构**：
```
SubagentLoader  →  SubagentConfig  →  SubagentRunner  →  Agent 实例
       ↑                                              ↓
  subagents/name/AGENT.md                    delegate_subagent (FunctionTool)
                                                     ↓
                                          Agent 内部调用 / Task API 外部调用
```

### 3.6 Context Compaction

AgentScope 2.0 内置 `compress_context()` 自动在每次 reasoning 前检测 token 使用量，超过阈值时触发结构化压缩。

**配置**：
- `trigger_ratio = 0.4`（40% of 128K = 51.2K tokens）
- `warning_tokens = 20000`（警告阈值）

**压缩摘要结构**：
- `task_overview` — 用户核心请求和成功标准
- `current_state` — 已完成的工作、文件变更
- `important_discoveries` — 技术约束、决策、错误修复
- `next_steps` — 待完成的具体行动
- `context_to_preserve` — 用户偏好、承诺

**流式可见性**：CLI 输出 `[Compaction] Context compressed, summary updated`，SSE 发送 `compaction` 事件。

### 3.7 Async Task API

通过 HTTP 提交异步任务，任务存储在 `.trae/tasks/` 目录，支持轮询状态。

**状态机**：`pending → running → completed/failed/cancelled`

**端点**：
```
POST   /api/tasks            → 提交任务
GET    /api/tasks/{task_id}  → 查询状态
GET    /api/tasks             → 列出所有
DELETE /api/tasks/{task_id}  → 取消任务
```

## 4. Key Interfaces

### 4.1 config.py

```python
class Config:
    deepseek_api_key: str
    deepseek_model: str          # default: "deepseek-v4-pro"
    deepseek_base_url: str       # default: "https://api.deepseek.com"
    permission_mode: str         # default: "bypass"
    chrome_mcp_enabled: bool     # default: True
    compaction_trigger_ratio: float  # default: 0.4
    compaction_warning_tokens: int   # default: 20000

def load_config() -> Config: ...
```

### 4.2 tools.py

```python
async def build_toolkit(config: Config) -> Toolkit: ...
# Returns Toolkit with 13 built-in tools + optional MCP + skills + subagents
```

### 4.3 agent.py

```python
async def build_agent(config: Config, toolkit: Toolkit) -> Agent: ...
# Returns fully configured Agent with ContextConfig + SubagentRunner
```

### 4.4 cli.py

```python
async def run_cli(agent: Agent) -> None: ...
# Interactive loop with event streaming + compaction detection
```

### 4.5 service.py

```python
def create_app(agent: Agent, task_manager: TaskManager | None = None) -> FastAPI: ...
# Returns FastAPI app with /chat, /stream, /api/files/*, /api/tasks/* endpoints
```

### 4.6 task_manager.py

```python
class TaskManager:
    def create(content: str, subagent: str | None = None) -> TaskRecord: ...
    def get(task_id: str) -> TaskRecord | None: ...
    def list_all() -> list[TaskRecord]: ...
    def update(task_id: str, **kwargs) -> TaskRecord | None: ...
    def delete(task_id: str) -> bool: ...
    async def execute(task: TaskRecord, agent: Agent) -> None: ...
    def start_execute(task: TaskRecord, agent: Agent) -> None: ...
```

### 4.7 subagent.py

```python
class SubagentLoader:
    def load(name: str) -> SubagentConfig | None: ...
    def list_all() -> dict[str, SubagentConfig]: ...

class SubagentRunner:
    async def run(subagent_name: str, task: str, context: str | None = None) -> str: ...

async def delegate_subagent(subagent_name: str, task: str, context: str | None = None) -> AsyncGenerator[ToolChunk, None]: ...
```

## 5. Entry Points

- `uv run main.py` — CLI mode
- `uv run python -m app.service` — Agent Service mode (HTTP API on :8000)
- `uv run pytest tests/ -v` — 58 unit tests

## 6. Extension Points

1. **New Tool** → Add to `tools.py` → `BUILTIN_TOOLS`
2. **New Skill** → Create `.py` in `skills/` or `SKILL.md` in `skills/*/`
3. **New Subagent** → Create `subagents/name/AGENT.md`
4. **New MCP** → Add to `tools.py` → `build_toolkit()`
5. **New Model** → Update `config.py` + `agent.py`
6. **New Entry Mode** → Create `app/new_mode.py`, import `build_agent()`