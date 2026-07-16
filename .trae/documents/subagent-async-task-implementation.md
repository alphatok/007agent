# Subagent + Async Task API 实施计划

## Summary

实现两个功能：
1. **Subagent 系统**：`delegate_subagent` FunctionTool，支持创建独立 Agent 实例执行专项任务
2. **异步任务 HTTP API**：`POST /api/tasks` + `GET /api/tasks/{id}`，任务状态存储在 `.trae/tasks/`

两个功能共享 `SubagentRunner` 核心引擎。

## Current State Analysis

### 现有架构

```
app/
├── config.py          # Config dataclass（deepseek_api_key, model, compaction 等）
├── tools.py           # build_toolkit() → Toolkit（12 个 built-in tools + skills)
├── agent.py           # build_agent(config, toolkit) → Agent（含 ContextConfig）
├── cli.py             # run_cli() → 流式事件循环
├── service.py         # FastAPI create_app(agent) → /chat, /chat/stream, /api/files/*
├── compaction.py      # context_status 工具
└── search.py          # web_search 工具
```

### 关键依赖

- `Agent` 类：`reply_stream(UserMsg("user", content))` 返回事件流
- `build_agent(config, toolkit)` → 创建 Agent 实例（async）
- `build_toolkit(config)` → 创建 Toolkit（async）
- `Agent.state.context` → 对话历史
- `Agent.state.summary` → 压缩摘要
- `Agent.name` → Agent 名称
- `TaskCreate/Get/List/Update` → AgentScope 内置 Task 工具

### 已有模式

- FunctionTool 模式：async generator → ToolChunk + TextBlock + ToolResultState
- 流式 SSE：`_sse()` 格式化 JSON → `text/event-stream`
- 配置驱动：.env → Config dataclass
- 测试模式：pytest + asyncio + unittest.mock

---

## Proposed Changes

### Phase 1: 异步任务 HTTP API（方案2）

#### 1.1 `app/task_manager.py` — 新增任务管理器

**What**: 创建 `TaskManager` 类，管理异步任务的生命周期

**Why**: 提供任务的 CRUD、状态查询、后台执行能力

**How**:
```python
# app/task_manager.py
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict

TASKS_DIR = Path(".trae/tasks")

@dataclass
class TaskRecord:
    task_id: str
    status: str  # pending | running | completed | failed | cancelled
    content: str
    subagent: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    result: str | None
    error: str | None

class TaskManager:
    def __init__(self, tasks_dir: Path = TASKS_DIR):
        self.tasks_dir = tasks_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
    
    def create(self, content: str, subagent: str | None = None) -> TaskRecord:
        ...
    
    def get(self, task_id: str) -> TaskRecord | None:
        ...
    
    def list_all(self) -> list[TaskRecord]:
        ...
    
    def update(self, task_id: str, **kwargs) -> TaskRecord | None:
        ...
    
    def delete(self, task_id: str) -> bool:
        ...
    
    async def execute(self, task: TaskRecord, agent: Agent) -> None:
        """后台执行任务，完成后更新状态"""
        ...
```

**文件存储**：`.trae/tasks/{task_id}.json`，每个任务一个文件

**状态机**：`pending → running → completed/failed/cancelled`

#### 1.2 `app/service.py` — 新增 4 个任务端点

**What**: 在 `create_app()` 中添加任务相关路由

**Why**: 提供 HTTP 接口提交和查询异步任务

**How**:
```python
# 在 create_app() 中添加：

@app.post("/api/tasks")
async def submit_task(request: dict) -> dict:
    """提交异步任务，立即返回 task_id"""
    ...

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """查询任务状态"""
    ...

@app.get("/api/tasks")
async def list_tasks() -> list[dict]:
    """列出所有任务"""
    ...

@app.delete("/api/tasks/{task_id}")
async def cancel_task(task_id: str) -> dict:
    """取消/删除任务"""
    ...
```

**关键改动**：
- `create_app()` 签名改为 `create_app(agent, task_manager)` 
- `main()` 中创建 `TaskManager` 实例并传入
- 任务执行时使用 `asyncio.create_task()` 后台运行，不阻塞 HTTP 响应

#### 1.3 `tests/test_task_api.py` — 新增测试

**What**: 测试任务管理器和 API 端点

**测试用例**:
1. `test_create_task` — 创建任务返回 task_id
2. `test_get_task_status` — 查询任务状态
3. `test_list_tasks` — 列出所有任务
4. `test_delete_task` — 删除任务
5. `test_task_state_transitions` — 状态转换 pending→running→completed
6. `test_task_persistence` — 任务数据持久化到 .trae/tasks/

---

### Phase 2: Subagent 系统（方案1）

#### 2.1 `subagents/` — 新增 Subagent 配置目录

**What**: 创建两个 Subagent 配置文件

**Why**: 遵循 Anthropic AGENT.md 规范，提供可复用的 Subagent 定义

**文件**:
- `subagents/code-reviewer/AGENT.md` — YAML frontmatter + 系统提示词
- `subagents/test-generator/AGENT.md` — YAML frontmatter + 系统提示词

**AGENT.md 格式**:
```yaml
---
name: code-reviewer
description: >-
  审查代码变更，检查代码质量、安全性、性能、可维护性。
  当用户要求审查代码、检查PR、评估代码质量时使用。
  不要用于简单的代码解释或文档生成。
tools: Read, Grep, Glob, Bash
model: deepseek-v4-pro
---
（系统提示词，Markdown 格式）
```

#### 2.2 `app/subagent.py` — 新增 Subagent 调度器

**What**: 创建 Subagent 配置加载、实例创建、执行运行的核心模块

**Why**: 提供 Subagent 的完整生命周期管理

**How**:
```python
# app/subagent.py

from dataclasses import dataclass
from pathlib import Path
from agentscope.agent import Agent
from agentscope.tool import FunctionTool, ToolChunk
from app.config import Config

SUBAgENTS_DIR = Path("subagents")

@dataclass
class SubagentConfig:
    name: str
    description: str
    tools: list[str]
    model: str
    system_prompt: str

class SubagentLoader:
    """从 subagents/ 目录加载 Subagent 配置"""
    
    def load(self, name: str) -> SubagentConfig | None:
        ...
    
    def list_all(self) -> dict[str, SubagentConfig]:
        ...

class SubagentRunner:
    """创建并运行 Subagent 实例"""
    
    def __init__(self, config: Config, loader: SubagentLoader):
        self.config = config
        self.loader = loader
    
    async def run(
        self, 
        subagent_name: str, 
        task: str,
        context: str | None = None,
    ) -> str:
        """创建独立 Agent 实例，执行任务，返回结果"""
        subagent_config = self.loader.load(subagent_name)
        if not subagent_config:
            raise ValueError(f"Subagent '{subagent_name}' not found")
        
        # 1. 创建精简 Toolkit（只包含白名单工具）
        # 2. 创建独立 Agent 实例
        # 3. 使用 agent.reply() 执行任务
        # 4. 返回结果文本
        ...

async def delegate_subagent(
    subagent_name: str,
    task: str,
    context: str | None = None,
) -> AsyncGenerator[ToolChunk, None]:
    """Delegate a task to a specialized subagent.
    
    Agent 可直接调用此工具，将任务委派给子代理。
    """
    # 获取 Config 和 SubagentRunner（通过闭包或全局变量）
    ...
```

**关键设计**：
- 工具白名单：Subagent 只获得配置中声明的工具（Read, Grep, Glob, Bash 等）
- 独立上下文：每个 Subagent 使用新的 AgentState
- 无 MCP：Subagent 不加载 MCP 客户端
- 无 Skills：Subagent 不加载 Skill 系统
- 结果返回：只返回 `agent.reply()` 的文本内容，不返回中间过程

#### 2.3 `app/tools.py` — 注册 delegate_subagent 工具

**What**: 将 `delegate_subagent` 注册到 Agent 的工具列表

**Why**: Agent 可以调用此工具委派任务

**How**:
```python
# app/tools.py
from app.subagent import delegate_subagent

BUILTIN_TOOLS = [
    # ... existing tools ...
    FunctionTool(delegate_subagent),
]
```

**注意**：`delegate_subagent` 需要访问 `SubagentRunner` 和 `Config`。由于 `build_toolkit` 在 `build_agent` 之前调用，需要延迟注入或使用全局变量。方案：在 `build_agent` 中创建 `SubagentRunner` 并注入到 `delegate_subagent` 的闭包中。

#### 2.4 `app/agent.py` — 建立 SubagentRunner 注入

**What**: 在 `build_agent()` 中创建 `SubagentRunner` 并注入到 `delegate_subagent`

**Why**: `delegate_subagent` 闭包需要访问 `SubagentRunner` 实例

**How**:
```python
# app/agent.py
from app.subagent import SubagentLoader, SubagentRunner, set_subagent_runner

async def build_agent(config: Config, toolkit: Toolkit) -> Agent:
    # 创建 SubagentRunner 并注入到 delegate_subagent 闭包
    loader = SubagentLoader()
    runner = SubagentRunner(config, loader)
    set_subagent_runner(runner, config)
    
    # ... 创建 Agent（不变）
```

#### 2.5 `tests/test_subagent.py` — 新增测试

**What**: 测试 Subagent 系统

**测试用例**:
1. `test_subagent_loader_loads_config` — 加载 AGENT.md 配置
2. `test_subagent_loader_returns_none_for_missing` — 不存在的 Subagent 返回 None
3. `test_subagent_loader_lists_all` — 列出所有 Subagent
4. `test_subagent_config_has_required_fields` — 配置包含必要字段
5. `test_subagent_runner_creates_agent` — Runner 创建 Agent 实例
6. `test_delegate_subagent_tool_yields_chunks` — 工具返回 ToolChunk

---

### 两个 Phase 的关系

```
                     SubagentRunner（核心引擎）
                    /                        \
    delegate_subagent (Tool)          TaskManager.execute(agent)
    (Agent 内部调用，同步等待)          (HTTP 后台执行，异步轮询)
           |                                    |
    Phase 2: subagent.py               Phase 1: task_manager.py
    Phase 2: subagents/AGENT.md        Phase 1: service.py 端点
    Phase 2: tools.py 注册              Phase 1: .trae/tasks/ 存储
```

---

## 文件变更汇总

| 文件 | Phase | 变更类型 |
|------|-------|----------|
| `app/task_manager.py` | 1 | **新增** — TaskManager + TaskRecord |
| `app/service.py` | 1 | **改造** — 新增 /api/tasks/* 端点 |
| `tests/test_task_api.py` | 1 | **新增** — 6 个测试 |
| `subagents/code-reviewer/AGENT.md` | 2 | **新增** — 代码审查 Subagent 配置 |
| `subagents/test-generator/AGENT.md` | 2 | **新增** — 测试生成 Subagent 配置 |
| `app/subagent.py` | 2 | **新增** — SubagentConfig/Loader/Runner/delegate |
| `app/tools.py` | 2 | **改造** — 注册 delegate_subagent |
| `app/agent.py` | 2 | **改造** — 创建 SubagentRunner 并注入 |
| `tests/test_subagent.py` | 2 | **新增** — 6 个测试 |

---

## Assumptions & Decisions

1. **Phase 1 先于 Phase 2**：异步任务 API 独立性强，先落地。Subagent 系统依赖 TaskManager 的执行模式
2. **Subagent 无 MCP/Skills**：为保持独立上下文干净，Subagent 不加载 MCP 和 Skill 系统
3. **工具白名单**：Subagent 只获得 AGENT.md 中声明的工具，不继承主 Agent 的全部工具
4. **.trae/tasks/ 存储**：与现有 .trae/memory/ 保持一致，使用项目级临时目录
5. **delegate_subagent 闭包注入**：通过 `set_subagent_runner()` 全局函数注入，避免复杂的依赖注入框架
6. **Subagent 使用相同模型**：默认使用 DeepSeek V4 Pro，与主 Agent 相同

## Verification

1. `uv run pytest tests/ -v` — 所有现有 + 新增测试通过
2. `curl -X POST http://localhost:8000/api/tasks -d '{"content":"test"}'` — 验证异步任务 API
3. `curl http://localhost:8000/api/tasks/{task_id}` — 验证状态查询
4. `uv run main.py` — CLI 中 Agent 可调用 `delegate_subagent` 工具