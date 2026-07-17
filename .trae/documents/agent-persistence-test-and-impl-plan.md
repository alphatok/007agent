# Agent 持久化 & 记忆系统 — 测试计划 + 实施计划

## 一、当前状态分析

### 现有模块
| 模块 | 路径 | 职责 |
|------|------|------|
| Config | `app/config.py` | 配置 dataclass，从 env 加载 |
| Agent | `app/agent.py` | `build_agent()` async 工厂 |
| Tools | `app/tools.py` | `build_toolkit()` async，13 个内置工具 |
| CLI | `app/cli.py` | 交互式终端，事件流显示 |
| Service | `app/service.py` | FastAPI + SSE 流式 + Web UI + 任务 API |
| Compaction | `app/compaction.py` | `context_status` FunctionTool |
| Subagent | `app/subagent.py` | SubagentLoader/Runner + delegate_subagent |
| TaskManager | `app/task_manager.py` | 异步任务 CRUD，`.trae/tasks/` JSON 持久化 |
| Search | `app/search.py` | DuckDuckGo web_search |

### 现有测试（10 个文件，58 个用例）
| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `test_config.py` | 3 | Config 加载和默认值 |
| `test_agent.py` | 4 | Agent 构建、system_prompt、skill 注入 |
| `test_tools.py` | 3 | Toolkit 构建、工具计数 |
| `test_cli.py` | 2 | CLI 入口 |
| `test_service.py` | 3 | App 创建、health 端点 |
| `test_compaction.py` | 8 | context_status 工具 |
| `test_subagent.py` | 9 | Loader、Runner、delegate_subagent |
| `test_task_api.py` | 11 | TaskManager CRUD + 持久化 |
| `test_search.py` | 3 | web_search 工具 |
| `test_skills.py` | 7 | Skill 发现和加载 |

### 测试模式约定
- **类组织**：`class TestXxx` 分组
- **异步**：`@pytest.mark.asyncio` + `async def`
- **环境变量**：`unittest.mock.patch.dict(os.environ, {...})`
- **临时目录**：`tempfile.TemporaryDirectory` + `pytest.fixture` + `yield`
- **工具测试**：`async for chunk in tool_func(...)` → 断言 `chunk.state` + `chunk.content[0].text`
- **断言风格**：简洁 `assert`，不依赖 `pytest.raises`

---

## 二、测试计划（测试先行）

### Phase 0：新增测试文件

#### 2.1 `tests/test_store.py` — 会话存储（12 用例）

```
TestSessionStore
├── test_init_creates_db          # 初始化应创建 SQLite 文件
├── test_init_enables_wal         # 应启用 WAL 模式
├── test_create_session           # 创建会话，返回 UUID
├── test_create_session_with_name # 创建命名会话
├── test_list_sessions            # 列出会话，按更新时间倒序
├── test_list_sessions_empty      # 无会话时返回空列表
├── test_get_session              # 获取会话元数据
├── test_get_session_nonexistent  # 不存在的会话返回 None
├── test_delete_session           # 删除会话，get 返回 None
├── test_delete_session_nonexistent # 删除不存在的会话返回 False
├── test_save_message             # 保存消息，更新 session message_count
├── test_save_message_with_tool_calls # 保存带 tool_calls 的消息（JSON 序列化）
├── test_get_messages             # 获取会话消息，按时间排序
├── test_get_messages_limit       # limit 参数限制返回数量
├── test_save_tool_log            # 保存工具调用日志
├── test_save_summary             # 保存/获取会话摘要
├── test_cleanup_old_sessions     # 清理超量/过期会话
├── test_persistence_across_instances # 重新打开 SessionStore，数据仍在
├── test_load_session_to_agent    # 将历史消息加载到 agent.state.context（Mock）
```

#### 2.2 `tests/test_embedding.py` — Embedding 层（6 用例）

```
TestEmbeddingProvider
├── test_fastembed_embed          # FastEmbed 生成 embedding（需安装 fastembed）
├── test_fastembed_output_shape   # 输出维度正确（384 维）
├── test_fastembed_output_type    # 输出是 float list
├── test_deepseek_embed_mock      # DeepSeek API 调用（Mock）
├── test_backend_switch           # embedding_backend 切换（fastembed ↔ deepseek）
├── test_embed_empty_string       # 空字符串处理
```

#### 2.3 `tests/test_memory.py` — 记忆存储（12 用例）

```
TestMemoryStore
├── test_add_memory               # 添加记忆，返回 ID
├── test_add_memory_writes_zvec   # 添加记忆后 zvec 中有数据
├── test_get_memory               # 获取记忆
├── test_get_memory_nonexistent   # 不存在的记忆返回 None
├── test_update_memory            # 更新记忆字段
├── test_delete_memory            # 删除记忆（SQLite + zvec 同步删除）
├── test_list_memories            # 列出记忆
├── test_list_memories_by_type    # 按类型过滤
├── test_memory_types             # episodic / semantic / procedural 三种类型
├── test_consolidate              # 巩固：高频 episodic → semantic
├── test_decay                    # 衰减：低重要性 + 长期未访问 → 删除
├── test_extract_from_session     # 从会话消息中提取记忆（Mock LLM 调用）
```

#### 2.4 `tests/test_retriever.py` — 混合检索（8 用例）

```
TestHybridRetriever
├── test_search_returns_results   # 搜索返回结果
├── test_search_empty_query       # 空查询处理
├── test_search_by_type           # 按 memory_type 过滤
├── test_search_min_importance    # 按重要性过滤
├── test_search_no_results        # 无匹配时返回空列表
├── test_search_ranked            # 结果按相关性排序
├── test_search_keyword           # 关键词匹配（zvec FTS）
├── test_search_semantic          # 语义匹配（zvec VectorQuery）
```

#### 2.5 `tests/test_memory_tool.py` — 记忆工具（6 用例）

```
TestMemoryTools
├── test_search_memory_tool       # search_memory 工具返回 SUCCESS
├── test_add_memory_tool          # add_memory 工具返回 SUCCESS
├── test_list_memories_tool       # list_memories 工具返回 SUCCESS
├── test_forget_memory_tool       # forget_memory 工具返回 SUCCESS
├── test_search_memory_nonexistent # 搜索不存在的记忆返回空
├── test_forget_memory_nonexistent # 删除不存在的记忆返回 ERROR
```

#### 2.6 `tests/test_store_integration.py` — 集成测试（4 用例）

```
TestIntegration
├── test_session_lifecycle        # 创建会话 → 保存消息 → 恢复 → 删除
├── test_memory_lifecycle         # 提取记忆 → 搜索 → 巩固 → 衰减
├── test_compaction_integration   # 压缩前消息已持久化到 SQLite
├── test_task_migration           # .trae/tasks/ → data/tasks/ 迁移
```

---

## 三、实施计划

### Phase 1：基础设施 + 数据目录迁移

**目标**：更新配置、依赖、.gitignore，迁移现有数据目录

| 步骤 | 文件 | 操作 |
|------|------|------|
| 1.1 | `pyproject.toml` | 添加 `zvec`、`fastembed` 依赖 |
| 1.2 | `app/config.py` | 新增 `data_dir`、`db_path`、`zvec_path`、`session_max_count`、`session_max_age_days`、`persistence_mode`、`memory_enabled`、`memory_extraction_enabled`、`memory_consolidation_threshold`、`memory_decay_days`、`embedding_backend`、`embedding_model_name` 字段 |
| 1.3 | `app/task_manager.py` | `TASKS_DIR` 从 `.trae/tasks` 改为 `data/tasks` |
| 1.4 | `.gitignore` | 添加 `data/` |
| 1.5 | Root | `uv add zvec fastembed` |

**验证**：`uv run pytest tests/test_config.py -v` 通过

### Phase 2：核心存储层 `app/store.py`

**目标**：实现 `SessionStore` 类，SQLite 持久化会话和消息

| 步骤 | 文件 | 操作 |
|------|------|------|
| 2.1 | `app/store.py` | 创建模块：`SessionStore.__init__`（建表、WAL、索引） |
| 2.2 | `app/store.py` | 会话 CRUD：`create_session`/`list_sessions`/`get_session`/`delete_session`/`cleanup_old_sessions` |
| 2.3 | `app/store.py` | 消息 CRUD：`save_message`/`get_messages`/`save_tool_log` |
| 2.4 | `app/store.py` | 摘要：`save_summary`/`get_summary` |
| 2.5 | `app/store.py` | 恢复：`load_session`/`resume_last_session` |

**验证**：`uv run pytest tests/test_store.py -v` 全部通过（19 用例）

### Phase 3：Embedding 层 `app/embedding.py`

**目标**：实现 `EmbeddingProvider`，FastEmbed 默认 + DeepSeek API 可选

| 步骤 | 文件 | 操作 |
|------|------|------|
| 3.1 | `app/embedding.py` | 创建模块：`EmbeddingProvider.__init__`（双后端） |
| 3.2 | `app/embedding.py` | `embed()` 方法（FastEmbed ONNX + DeepSeek API） |

**验证**：`uv run pytest tests/test_embedding.py -v` 全部通过（6 用例）

### Phase 4：记忆存储层 `app/memory.py`

**目标**：实现 `MemoryStore`，CRUD + 生命周期管理 + zvec 同步

| 步骤 | 文件 | 操作 |
|------|------|------|
| 4.1 | `app/memory.py` | 创建模块：`MemoryStore.__init__`（建 memories 表、zvec collection） |
| 4.2 | `app/memory.py` | 记忆 CRUD：`add_memory`/`get_memory`/`update_memory`/`delete_memory`/`list_memories` |
| 4.3 | `app/memory.py` | zvec 同步：`sync_to_zvec`（写入向量 + FTS 索引）、`rebuild_index`（启动时全量重建） |
| 4.4 | `app/memory.py` | 生命周期：`extract_from_session`（LLM 提取）、`consolidate`（episodic → semantic）、`decay`（过期清理） |

**验证**：`uv run pytest tests/test_memory.py -v` 全部通过（12 用例）

### Phase 5：混合检索 `app/retriever.py`

**目标**：实现 `HybridRetriever`，基于 zvec MultiQuery 的混合检索

| 步骤 | 文件 | 操作 |
|------|------|------|
| 5.1 | `app/retriever.py` | 创建模块：`HybridRetriever.__init__`（加载 zvec collection + EmbeddingProvider） |
| 5.2 | `app/retriever.py` | `search()` 方法：zvec MultiQuery（VectorQuery + FTSQuery + filter） |

**验证**：`uv run pytest tests/test_retriever.py -v` 全部通过（8 用例）

### Phase 6：记忆工具 `app/memory_tool.py`

**目标**：实现 Agent 可调用的记忆 FunctionTool

| 步骤 | 文件 | 操作 |
|------|------|------|
| 6.1 | `app/memory_tool.py` | 创建模块：`search_memory`/`add_memory`/`list_memories`/`forget_memory` async generator |
| 6.2 | `app/memory_tool.py` | `get_tools()` 返回 4 个 FunctionTool |
| 6.3 | `app/tools.py` | 注册 `get_memory_tools()` 到 `BUILTIN_TOOLS` |

**验证**：`uv run pytest tests/test_memory_tool.py -v` 全部通过（6 用例）

### Phase 7：Agent 集成

**目标**：将 SessionStore + MemoryStore 注入 Agent，实现消息钩子 + 会话恢复

| 步骤 | 文件 | 操作 |
|------|------|------|
| 7.1 | `app/agent.py` | `build_agent()` 接受 `store: SessionStore \| None`、`memory: MemoryStore \| None` |
| 7.2 | `app/agent.py` | 注入到 agent 实例（`_store`、`_memory`） |
| 7.3 | `app/cli.py` | 启动时创建 SessionStore/MemoryStore，注入 agent |
| 7.4 | `app/cli.py` | 启动时展示会话管理菜单（新建/恢复/删除） |
| 7.5 | `app/cli.py` | 每次交互后自动保存消息到 SQLite |
| 7.6 | `app/cli.py` | 压缩检测后触发记忆提取 |
| 7.7 | `app/cli.py` | 退出时清理过期会话和记忆 |
| 7.8 | `app/service.py` | `main()` 创建 SessionStore/MemoryStore，注入 agent |

**验证**：`uv run pytest tests/test_store_integration.py -v` 全部通过（4 用例）

### Phase 8：HTTP API

**目标**：新增会话和记忆管理端点

| 步骤 | 文件 | 操作 |
|------|------|------|
| 8.1 | `app/service.py` | `create_app()` 接受 `store: SessionStore \| None`、`memory: MemoryStore \| None` |
| 8.2 | `app/service.py` | 新增 6 个会话端点（GET/POST/DELETE sessions） |
| 8.3 | `app/service.py` | 新增 4 个记忆端点（GET/POST/DELETE memories + search） |

**验证**：`uv run pytest tests/test_service.py -v` 更新后通过

### Phase 9：测试回归 + 文档

**目标**：确保所有现有测试通过，更新文档

| 步骤 | 文件 | 操作 |
|------|------|------|
| 9.1 | `tests/test_tools.py` | 更新 `test_builtin_tool_count`：13 → 17（新增 4 个 memory tools） |
| 9.2 | `tests/test_config.py` | 新增 config 字段测试 |
| 9.3 | 全量 | `uv run pytest -v` 确保零失败 |
| 9.4 | `README.md` | 更新功能和架构 |
| 9.5 | `docs/architecture.md` | 更新模块依赖图 |

---

## 四、关键设计决策

1. **zvec 作为单例**：`MemoryStore` 和 `HybridRetriever` 共享同一个 zvec collection，通过 `zvec.create_and_open(path=...)` 打开
2. **SQLite 连接管理**：`SessionStore` 和 `MemoryStore` 共享同一个 `sqlite3.Connection`（或各自独立连接，WAL 模式支持并发读）
3. **记忆提取时机**：在 `compress_context()` 触发后，对旧消息调用 `MemoryStore.extract_from_session()`
4. **zvec FTS 索引**：在 `content` 字段上建 FTS 索引，支持中文分词
5. **Embedding 维度**：FastEmbed BGE-small-zh 输出 384 维，zvec schema 使用 `VECTOR_FP32, 384`
6. **数据目录**：`data/` 不隐藏，与项目同级
7. **现有 TaskManager 迁移**：`.trae/tasks/` → `data/tasks/`，保留向后兼容（如果 `.trae/tasks/` 存在则迁移）

---

## 五、预计新增文件

| 文件 | 行数（估） |
|------|----------|
| `app/store.py` | ~200 |
| `app/embedding.py` | ~60 |
| `app/memory.py` | ~200 |
| `app/retriever.py` | ~80 |
| `app/memory_tool.py` | ~120 |
| `tests/test_store.py` | ~200 |
| `tests/test_embedding.py` | ~80 |
| `tests/test_memory.py` | ~200 |
| `tests/test_retriever.py` | ~120 |
| `tests/test_memory_tool.py` | ~100 |
| `tests/test_store_integration.py` | ~80 |

**总新增代码**：~1,440 行（含测试 ~780 行）

**新增测试用例**：48 个（从 58 → 106）

---

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| zvec 安装失败 | 回退到 Chroma（原方案），代码通过 `EmbeddingProvider` 抽象 |
| fastembed 模型下载慢 | 首次启动时提示用户，模型缓存到 `~/.cache/fastembed` |
| 记忆提取质量差 | `memory_extraction_enabled` 默认 True 但可关闭 |
| 现有测试回归 | Phase 9 全量回归，逐 Phase 验证 |