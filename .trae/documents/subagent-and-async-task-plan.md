# Subagent 设计规范 & 异步任务 API 方案

---

## 方案1：Subagent 设计与规范

### 1. 行业调研

#### 1.1 Anthropic Claude Code Subagent 机制

Anthropic 2025年9月推出 Subagent 功能，核心设计如下：

**定义**：Subagent 是预配置的专用 AI 助手，每个运行在自己的独立上下文中，拥有特定工具权限和系统提示词。

**核心优势**：
- **独立上下文**：每个 Subagent 拥有独立上下文窗口，中间过程不污染主对话
- **并行处理**：多个 Subagent 可同时执行，互不阻塞
- **专精任务**：每个 Subagent 有独立人设和系统提示词，专注于特定领域

**触发方式**：
1. **自动委派**：通过 `description` 字段描述能力，主 Agent 自动判断何时调用
2. **手动点名**：用户直接指定调用某个 Subagent

**配置结构**（`.claude/agents/name.md`）：
```yaml
---
name: code-reviewer
description: 审查代码变更，检查代码质量、安全性、性能问题
tools: Read, Grep, Glob, Bash
model: claude-sonnet-4-5-20250929
---
# System Prompt
你是一个专业的代码审查专家...
```

**何时使用 Subagent（Anthropic 官方建议）**：
- 需要独立上下文空间的任务（大量搜索/分析）
- 可并行执行的独立子任务
- 需要不同工具权限配制的任务
- 需要不同系统提示词/人设的专项任务

**何时不该使用**：
- 简单任务（创建 Subagent 本身有开销）
- 需要主对话完整上下文的任务
- 任务间有强依赖关系
- 对话很短，不值得拆

#### 1.2 Cursor Subagent 模式

Cursor 的 Subagent 通过 `description` 字段实现自动路由，关键设计：
- **清晰的任务边界**：明确输入输出格式
- **工具白名单**：限制 Subagent 可使用的工具
- **结果回收**：Subagent 只返回最终结果，不返回中间过程

#### 1.3 AgentScope 内置支持

AgentScope 2.0 提供了 Task 管理系统作为 Subagent 的基础：
- `TaskCreate`：创建任务（含 subject、description、metadata）
- `TaskGet/TaskList`：查询任务状态
- `TaskUpdate`：更新任务状态、依赖关系、所有权
- 任务状态：pending → in_progress → completed / deleted
- 支持依赖关系：blocks / blockedBy

AgentScope 的 Task 工具设计为**单 Agent 内部任务管理**，不直接支持创建独立 Agent 实例。但可以通过以下方式扩展：
- 使用 Task.metadata 存储 Subagent 配置
- 通过 Agent 工厂函数创建独立 Agent 实例
- 利用 Task 状态跟踪 Subagent 执行进度

---

### 2. 本项目 Subagent 设计方案

#### 2.1 架构设计

```
┌─────────────────────────────────────────────────────┐
│                    Main Agent                        │
│  ┌──────────────────────────────────────────────┐   │
│  │  Subagent 调度器                               │   │
│  │  - 读取 Subagent 配置                         │   │
│  │  - 创建 Agent 实例                            │   │
│  │  - 管理执行生命周期                            │   │
│  │  - 收集结果                                    │   │
│  └──────────────┬───────────────────────────────┘   │
│                 │ TaskCreate("subagent:xxx")         │
│                 ▼                                    │
│  ┌──────────────────────────────────────────────┐   │
│  │  Subagent Agent 实例                          │   │
│  │  - 独立上下文（新 AgentState）                 │   │
│  │  - 独立工具集（可裁剪）                        │   │
│  │  - 专用系统提示词                              │   │
│  │  - 结果回传 → TaskUpdate + metadata            │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

#### 2.2 Subagent 配置规范

沿用 Anthropic 的 YAML frontmatter 规范，存储在 `subagents/` 目录：

```
subagents/
├── code-reviewer/
│   └── AGENT.md
├── test-generator/
│   └── AGENT.md
└── web-researcher/
    └── AGENT.md
```

**AGENT.md 格式**：
```yaml
---
name: code-reviewer
description: >-
  审查代码变更，检查代码质量、安全性、性能、可维护性。
  当用户要求审查代码、检查PR、评估代码质量时使用。
  不要用于简单的代码解释或文档生成。
model: deepseek-v4-pro
tools: Read, Grep, Glob, Bash, Edit
permission: bypass
---
你是一个专业的代码审查专家。你的职责是：
1. 系统性审查代码变更
2. 检查代码质量、安全性、性能和可维护性
3. 提供具体的改进建议
4. 输出结构化的审查报告

审查流程：
1. 使用 Read 工具读取目标文件
2. 使用 Grep 搜索潜在问题
3. 按维度逐一检查
4. 生成审查报告
```

#### 2.3 新增 Subagent Tool

创建 `delegate_subagent` FunctionTool，对 Agent 暴露：

```python
async def delegate_subagent(
    subagent_name: str,
    task: str,
    context: str | None = None,
) -> AsyncGenerator[ToolChunk, None]:
    """Delegate a task to a specialized subagent.

    Args:
        subagent_name: Name of the subagent to invoke (e.g., "code-reviewer").
        task: The specific task description for the subagent.
        context: Optional additional context to pass to the subagent.
    """
    # 1. 加载 Subagent 配置
    # 2. 创建 Task 记录
    # 3. 创建独立 Agent 实例
    # 4. 异步执行
    # 5. 收集结果
    # 6. 更新 Task 状态
    # 7. 返回结果
```

#### 2.4 新增模块

```
app/
├── subagent.py          # 新增：Subagent 调度器
│   ├── SubagentConfig       # Subagent 配置模型
│   ├── SubagentLoader       # 从 subagents/ 加载配置
│   ├── SubagentRunner       # 创建并运行 Subagent 实例
│   └── delegate_subagent()  # FunctionTool 工具函数
│
subagents/               # 新增：Subagent 配置目录
├── code-reviewer/
│   └── AGENT.md
└── test-generator/
    └── AGENT.md
```

#### 2.5 最佳实践规范

| 规范 | 说明 |
|------|------|
| 每个 Subagent 一个职责 | 单一职责，专注一个领域 |
| 工具白名单 | 只授予必要的工具，最小权限原则 |
| 独立上下文 | 每个 Subagent 使用独立 AgentState |
| 结构化输出 | 输出格式在 AGENT.md 中明确定义 |
| 超时控制 | 设置合理的执行超时 |
| 结果裁剪 | 只返回关键结果，不返回中间过程 |
| 任务追踪 | 使用 Task 系统追踪执行状态 |

#### 2.6 改造点

| 文件 | 变更 |
|------|------|
| `app/subagent.py` | **新增** — Subagent 调度器 |
| `app/tools.py` | 注册 `delegate_subagent` 工具 |
| `subagents/code-reviewer/AGENT.md` | **新增** — 代码审查 Subagent |
| `subagents/test-generator/AGENT.md` | **新增** — 测试生成 Subagent |
| `tests/test_subagent.py` | **新增** — Subagent 测试 |

---

## 方案2：异步任务 HTTP API

### 1. 需求分析

提供 HTTP 接口支持：
- **提交异步任务**：POST 提交任务，立即返回任务 ID
- **查询任务状态**：GET 通过 ID 查询状态和结果
- **存储**：任务状态存储在项目临时目录（`.trae/tasks/`）

### 2. API 设计

#### 2.1 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks` | 提交异步任务 |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态 |
| `GET` | `/api/tasks` | 列出所有任务 |
| `DELETE` | `/api/tasks/{task_id}` | 取消/删除任务 |

#### 2.2 请求/响应格式

**POST /api/tasks**
```json
// Request
{
    "content": "帮我分析 app/ 目录下所有 Python 文件的代码质量",
    "mode": "async",
    "subagent": "code-reviewer"
}

// Response (201 Created)
{
    "task_id": "a1b2c3d4-...",
    "status": "pending",
    "created_at": "2026-07-17T10:30:00Z",
    "status_url": "/api/tasks/a1b2c3d4-..."
}
```

**GET /api/tasks/{task_id}**
```json
// Response
{
    "task_id": "a1b2c3d4-...",
    "status": "running",
    "content": "帮我分析 app/ 目录下所有 Python 文件的代码质量",
    "created_at": "2026-07-17T10:30:00Z",
    "started_at": "2026-07-17T10:30:01Z",
    "result": null
}
```

```json
// Completed
{
    "task_id": "a1b2c3d4-...",
    "status": "completed",
    "content": "帮我分析 app/ 目录下所有 Python 文件的代码质量",
    "created_at": "2026-07-17T10:30:00Z",
    "started_at": "2026-07-17T10:30:01Z",
    "completed_at": "2026-07-17T10:32:15Z",
    "result": "## 代码质量分析报告\n\n..."
}
```

**Task 状态机**：
```
pending → running → completed
                  → failed
         → cancelled
```

#### 2.3 存储设计

任务存储在 `.trae/tasks/` 目录，每个任务一个 JSON 文件：

```
.trae/tasks/
├── a1b2c3d4-5678-90ab-cdef-1234567890ab.json
├── b2c3d4e5-6789-01ab-cdef-2345678901bc.json
└── ...
```

**JSON 文件结构**：
```json
{
    "task_id": "a1b2c3d4-...",
    "status": "completed",
    "content": "帮我分析 app/ 目录...",
    "subagent": "code-reviewer",
    "created_at": "2026-07-17T10:30:00Z",
    "started_at": "2026-07-17T10:30:01Z",
    "completed_at": "2026-07-17T10:32:15Z",
    "result": "## 代码质量分析报告\n\n...",
    "error": null
}
```

#### 2.4 改造点

| 文件 | 变更 |
|------|------|
| `app/service.py` | **改造** — 新增 4 个任务端点 |
| `app/task_manager.py` | **新增** — 任务管理器（CRUD + 异步执行） |
| `tests/test_task_api.py` | **新增** — 任务 API 测试 |

#### 2.5 实现要点

- 使用 `asyncio.create_task()` 在后台执行 Agent 对话
- 文件锁避免并发写入冲突
- 任务完成后自动清理（可选，保留 24 小时）
- 与 Subagent 系统集成：任务可指定使用哪个 Subagent 执行

---

## 两个方案的关系

```
方案1（Subagent）            方案2（Async Task API）
┌──────────────────┐        ┌──────────────────────┐
│ delegate_subagent │        │ POST /api/tasks       │
│ FunctionTool      │        │ GET /api/tasks/{id}   │
│                   │        │                       │
│ Agent 内部调用     │   →    │ 外部 HTTP 调用        │
│ 同步等待结果       │        │ 异步轮询结果          │
│ 通过 Task 追踪     │        │ 通过 .trae/tasks/ 存储│
└──────────────────┘        └──────────────────────┘
          │                           │
          └───────────┬───────────────┘
                      ▼
          ┌──────────────────────┐
          │  SubagentRunner      │
          │  - 创建 Agent 实例    │
          │  - 独立上下文执行     │
          │  - 结果回收           │
          └──────────────────────┘
```

两个方案共享 `SubagentRunner` 核心，区别在于触发方式：
- 方案1：Agent 通过 tool 调用（内部触发）
- 方案2：用户通过 HTTP API 调用（外部触发）

---

## 实施优先级

1. **Phase 1**：方案2 — 异步任务 API（独立性强，可先落地）
2. **Phase 2**：方案1 — Subagent 系统（依赖 Task API 和 SubagentRunner）
3. **Phase 3**：两个方案集成，共享 SubagentRunner