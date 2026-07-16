# AgentScope Agent - Architecture Design

## 1. Overview

An AI Agent application powered by DeepSeek V4 Pro, supporting both CLI and
Web UI (AgentScope Studio) interaction modes with a shared agent core.

## 2. Architecture

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

## 3. Module Design

```
app/
├── __init__.py
├── config.py          # Config: load .env, typed settings
├── tools.py           # Tools:  register all built-in + MCP tools
├── search.py          # Search: DuckDuckGo web search tool
├── agent.py           # Agent:  build_agent() factory
├── cli.py             # CLI:    interactive terminal loop
└── service.py         # Service: FastAPI app for Studio mode

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
| `tools.py` | Build Toolkit with built-in + MCP + skills | `agentscope.tool`, `agentscope.mcp`, `skills` |
| `search.py` | DuckDuckGo web search tool | `duckduckgo-search` |
| `agent.py` | Create Agent instance from config + tools | `config`, `tools` |
| `cli.py` | Interactive CLI loop with event streaming | `agent` |
| `service.py` | FastAPI app with REST + SSE + Web UI | `agent` |

### 3.2 Dependency Flow

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

### 3.3 Design Principles

- **High Cohesion**: Each module has one clear responsibility
- **Low Coupling**: Modules depend only on what they need, via interfaces
- **Extensible**: Add new tools in `tools.py`, new skills in `skills/`, new modes as new entry points
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

## 4. Key Interfaces

### 4.1 config.py

```python
class Config:
    deepseek_api_key: str
    deepseek_model: str          # default: "deepseek-v4-pro"
    deepseek_base_url: str       # default: "https://api.deepseek.com"
    permission_mode: str         # default: "bypass"
    chrome_mcp_enabled: bool     # default: True

def load_config() -> Config: ...
```

### 4.2 tools.py

```python
async def build_toolkit(config: Config) -> Toolkit: ...
# Returns Toolkit with built-in tools + optional Chrome DevTools MCP
```

### 4.3 agent.py

```python
def build_agent(config: Config, toolkit: Toolkit) -> Agent: ...
# Returns fully configured Agent instance
```

### 4.4 cli.py

```python
async def run_cli(agent: Agent) -> None: ...
# Interactive loop with event streaming display
```

### 4.5 service.py

```python
def create_app(agent: Agent) -> FastAPI: ...
# Returns FastAPI app with /chat and /stream endpoints
```

## 5. Entry Points

- `python -m app.cli` — CLI mode (current behavior)
- `python -m app.service` — Agent Service mode (Studio-ready)

## 6. Extension Points

1. **New Tool**: Add to `tools.py` → `build_toolkit()`
2. **New MCP**: Add to `tools.py` → `build_toolkit()`
3. **New Model**: Update `config.py` + `agent.py`
4. **New Entry Mode**: Create `app/new_mode.py`, import `build_agent()`