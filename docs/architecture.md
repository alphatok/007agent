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
├── agent.py           # Agent:  build_agent() factory
├── cli.py             # CLI:    interactive terminal loop
└── service.py         # Service: FastAPI app for Studio mode
```

### 3.1 Module Responsibilities

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `config.py` | Load .env, provide typed config | `python-dotenv` |
| `tools.py` | Build Toolkit with built-in + MCP tools | `agentscope.tool`, `agentscope.mcp` |
| `agent.py` | Create Agent instance from config + tools | `config`, `tools` |
| `cli.py` | Interactive CLI loop with event streaming | `agent` |
| `service.py` | FastAPI app with REST + SSE endpoints | `agent` |

### 3.2 Dependency Flow

```
config.py           (no deps)
    │
    ▼
tools.py  ◄──────── config.py
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
- **Extensible**: Add new tools in `tools.py`, new modes as new entry points
- **Not Over-Engineered**: 6 modules, no abstract base classes without need

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