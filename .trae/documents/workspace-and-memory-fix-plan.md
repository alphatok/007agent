# Workspace & Memory Fix Plan

## Summary

1. 将工作目录从 `Path.cwd()`（当前 `/Users/bruceyang/`）改为项目目录下的 `workspace/` 文件夹
2. 修复记忆功能：补充 `update_memory` 工具、去重合并逻辑、操作日志、System Prompt 引导

---

## Phase 1: Workspace 路径优化

### 1.1 现状分析

| 文件 | 当前行为 | 问题 |
|------|---------|------|
| [service.py](file:///Users/bruceyang/AGENTS/app/service.py#L35) | `WORKSPACE_ROOT = Path.cwd()` | 硬编码为当前工作目录 `/Users/bruceyang/` |
| [service.py](file:///Users/bruceyang/AGENTS/app/service.py#L86) | `root = workspace_root or WORKSPACE_ROOT` | `create_app()` 支持参数但 `main()` 未传入 |
| [service.py](file:///Users/bruceyang/AGENTS/app/service.py#L644-L646) | `create_app(agent, task_manager=tm, store=store, memory=memory)` | 未传 `workspace_root` |
| [config.py](file:///Users/bruceyang/AGENTS/app/config.py) | 无 `workspace_root` 配置项 | 缺少统一配置 |

### 1.2 改动

**Step 1 - [config.py](file:///Users/bruceyang/AGENTS/app/config.py)**

在 `Config` dataclass 末尾新增 `workspace_root` 字段：

```python
# ---- Workspace ----
workspace_root: str = "workspace"
"""Workspace root directory for file operations. Relative to project root."""
```

在 `load_config()` 中新增加载：

```python
workspace_root=os.getenv("WORKSPACE_ROOT", "workspace"),
```

**Step 2 - [service.py](file:///Users/bruceyang/AGENTS/app/service.py)**

- 删除 `WORKSPACE_ROOT = Path.cwd()` 常量
- `main()` 中传入 `workspace_root` 给 `create_app()`：

```python
workspace_root = Path(config.workspace_root).resolve()
workspace_root.mkdir(parents=True, exist_ok=True)
app = create_app(
    agent, task_manager=tm, store=store, memory=memory,
    workspace_root=workspace_root,
)
```

- `create_app()` 中 `root = workspace_root or WORKSPACE_ROOT` 改为 `root = workspace_root`（不再依赖已删除的常量）

**Step 3 - 创建 `workspace/` 目录**

在项目根目录创建 `workspace/.gitkeep`，确保目录跟随版本控制。

**Step 4 - [.gitignore](file:///Users/bruceyang/AGENTS/.gitignore)**

已有 `.gitignore` 则追加，否则新建：

```
workspace/*
!workspace/.gitkeep
```

---

## Phase 2: 记忆功能修复

### 2.1 现状分析

| 组件 | 状态 | 问题 |
|------|------|------|
| `MemoryStore.add_memory()` | 正常 | 无去重，重复添加产生多条记录 |
| `MemoryStore.update_memory()` | 后端已实现 | **无对应 Agent 工具**，Agent 无法更新记忆 |
| `_extract_with_llm()` | 空实现（返回 `[]`） | 自动提取不可用 |
| `HybridRetriever.search()` | 仅 SQLite LIKE | 未使用 zvec 向量搜索，语义检索弱 |
| Agent System Prompt | 无记忆相关指令 | Agent 不知道要主动管理记忆 |
| 操作日志 | 无 | 新增/更新/删除记忆无日志记录 |

### 2.2 改动

**Step 5 - [memory.py](file:///Users/bruceyang/AGENTS/app/memory.py) — 去重逻辑**

在 `add_memory()` 方法中新增去重检查：添加前先查询是否存在相似内容（content 完全匹配），若存在则更新 importance（取 max）和 access_count（+1），而不是创建重复记录。

同时在 `add_memory()` 和 `update_memory()` 和 `delete_memory()` 中增加 `logging` 日志输出。

```python
import logging
logger = logging.getLogger(__name__)

def add_memory(self, type, content, ...):
    # 去重：检查 content 完全匹配的已有记忆
    existing = self._conn.execute(
        "SELECT id, importance, access_count FROM memories WHERE content = ?",
        (content,)
    ).fetchone()
    if existing:
        # 更新已有记忆
        new_importance = max(existing["importance"], importance)
        self._conn.execute(
            "UPDATE memories SET importance = ?, access_count = access_count + 1, updated_at = ? WHERE id = ?",
            (new_importance, _now(), existing["id"])
        )
        self._conn.commit()
        logger.info("[Memory] Merged duplicate: '%s...' (id: %s)", content[:50], existing["id"][:8])
        return existing["id"]
    # ... 原有新增逻辑
    logger.info("[Memory] Added %s: '%s...' (id: %s, importance: %.1f)", type, content[:50], memory_id[:8], importance)
```

**Step 6 - [memory_tool.py](file:///Users/bruceyang/AGENTS/app/memory_tool.py) — 新增 `_update_memory` 工具**

在现有 4 个工具（search/add/list/forget）基础上新增第 5 个：

```python
async def _update_memory(memory_id: str, content: str | None = None,
                         type: str | None = None,
                         importance: float | None = None) -> ToolChunk:
    """Update an existing memory's content, type, or importance.

    Args:
        memory_id: ID of the memory to update (use list_memories to find IDs).
        content: New content (optional).
        type: New type: episodic | semantic | procedural (optional).
        importance: New importance score 0.0-1.0 (optional).
    """
    # ... yield RUNNING, call _store.update_memory(), yield SUCCESS/ERROR
```

在 `get_memory_tools()` 中注册：

```python
FunctionTool(_update_memory),
```

**Step 7 - [agent.py](file:///Users/bruceyang/AGENTS/app/agent.py) — System Prompt 补充记忆指令**

在 `SYSTEM_PROMPT` 末尾追加记忆相关指令：

```python
"\n\n"
"## Memory Management\n"
"You have access to a cross-session memory system. Use it to:\n"
"- When the user tells you to remember something (e.g., '记住我叫XXX'), "
"use add_memory to store it.\n"
"- Before answering questions about the user, search memory first with "
"search_memory to recall past facts.\n"
"- When the user provides updated information, use update_memory to "
"modify existing memories instead of creating duplicates.\n"
"- Use list_memories to review what you already know about the user.\n"
"- Use forget_memory to remove outdated or incorrect memories.\n"
"- Memory types: 'semantic' for facts/preferences, 'episodic' for "
"events/experiences, 'procedural' for workflows/instructions."
```

**Step 8 - [retriever.py](file:///Users/bruceyang/AGENTS/app/retriever.py) — 向量搜索增强**

`search()` 方法当前仅使用 SQLite LIKE 关键词匹配。改为优先尝试 zvec 向量搜索，失败时 fallback 到 SQLite LIKE：

```python
def search(self, query, top_k=10, memory_types=None, min_importance=0.0):
    # 尝试 zvec 向量搜索
    if self._zvec_collection is not None:
        try:
            return self._zvec_search(query, top_k, memory_types, min_importance)
        except Exception:
            pass
    # fallback: SQLite LIKE
    return self._sqlite_search(query, top_k, memory_types, min_importance)
```

（注：zvec 向量搜索需要先生成 embedding 再查询，若 `EmbeddingProvider` 加载失败则自动 fallback 到 SQLite LIKE）

---

## Phase 3: 验证

| 序号 | 验证项 | 方法 |
|------|--------|------|
| 1 | `workspace/` 目录创建 | `ls workspace/` |
| 2 | 文件下载安全边界 | 启动服务，尝试下载 `workspace/` 外的文件应返回 403 |
| 3 | `node --check` JS 语法 | `node --check app/static/chat.js` |
| 4 | pytest 全量 | `uv run python -m pytest tests/ -v` |
| 5 | 记忆去重 | 调用 `add_memory` 两次相同内容，验证只产生一条记录 |
| 6 | `update_memory` 工具 | Agent 调用 `update_memory` 更新已有记忆 |
| 7 | 记忆日志 | 检查日志输出中 `[Memory]` 前缀的日志行 |
| 8 | 服务启动 | `uv run python -m app.service` 启动后 `/health` 正常响应 |

---

## 涉及文件总览

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| [config.py](file:///Users/bruceyang/AGENTS/app/config.py) | 修改 | 新增 `workspace_root` 配置项 |
| [service.py](file:///Users/bruceyang/AGENTS/app/service.py) | 修改 | 删除 `WORKSPACE_ROOT` 常量，`main()` 传入 `workspace_root` |
| workspace/.gitkeep | 新建 | 确保 `workspace/` 目录被 git 跟踪 |
| .gitignore | 修改 | 排除 `workspace/*` 但保留 `.gitkeep` |
| [memory.py](file:///Users/bruceyang/AGENTS/app/memory.py) | 修改 | 去重逻辑 + 日志 |
| [memory_tool.py](file:///Users/bruceyang/AGENTS/app/memory_tool.py) | 修改 | 新增 `_update_memory` 工具 |
| [agent.py](file:///Users/bruceyang/AGENTS/app/agent.py) | 修改 | System Prompt 补充记忆指令 |
| [retriever.py](file:///Users/bruceyang/AGENTS/app/retriever.py) | 修改 | 向量搜索增强 |

---

## 假设与决策

1. **workspace 目录命名**：使用 `workspace/`（小写），与 AGENTS 项目风格一致
2. **去重策略**：仅按 `content` 完全匹配去重，不涉及语义相似度（避免误判）
3. **zvec 向量搜索**：尝试使用 zvec 向量搜索，若 EmbeddingProvider 不可用则自动 fallback 到 SQLite LIKE，不影响现有功能
4. **`_extract_with_llm`**：本次不实现自动提取（用户未要求），仅修复手动记忆管理功能
5. **日志级别**：使用 `logging.info` 级别记录记忆操作，与项目现有日志风格一致