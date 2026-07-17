# Agent 历史记录持久化 & 记忆系统方案

## 一、业界实践调研

### 1.1 Codex CLI（OpenAI）

**配置方式**：`~/.codex/config.toml` 中的 `[history]` 段

```toml
[history]
persistence = "local"          # local | none | cloud | save-all
max_sessions = 50              # 最大保留会话数
max_session_age_days = 30      # 会话最大保留天数
auto_save_interval_seconds = 30 # 自动保存间隔
max_bytes = 104857600          # 100MB 上限
```

**核心设计**：
- 存储层：本地文件系统 + 内存缓存
- 会话粒度：每个会话独立存储
- 自动保存：定时快照（30s 间隔），异常退出不丢数据
- 容量控制：会话数量上限 + 过期清理 + 存储空间上限
- 上下文管理：compaction（压缩）技术，保留关键上下文
- 三层架构：Model 层 → Harness/Agent 层 → 连接真实环境

**关键点**：
- `save-all` 模式：保存完整对话历史（包括所有工具调用和结果）
- `local` 模式：仅保存用户消息和助手回复，不保存工具调用中间结果
- 支持多会话并行 + 命名会话
- 设计哲学：**"不做过度设计，但关键路径不能丢数据"**

### 1.2 Claude Code（Anthropic）

**存储结构**：

```
~/.config/claude/
├── claude.yaml                  # 全局配置
├── sessions/
│   ├── session_2025-11-25-153200.json
│   ├── session_projectA.json
│   └── last_session.json        # 快速恢复上一次会话
└── history/
    ├── chat_logs/               # 追加式 JSONL 日志
    └── system_messages/
```

**核心设计**：
- 存储格式：每个会话 = 独立 JSON 文件
- 追加式日志：`chat_logs/` 下使用 JSONL，每行一条消息
- 自动快照：对话结束后自动写回会话文件
- 上下文裁剪：恢复时保留最近 N 轮（10-20 轮），早期上下文用摘要替代
- 会话管理：`claude sessions list` / `claude sessions delete` / `claude chat --session <name>`
- 无状态 API：客户端本地存储状态，API 调用保持 stateless

**源码架构**（泄露分析）：
- `session_storage.ts`：会话存储层
- `history.ts`：历史记录管理
- 追加式 JSONL 会话记录 + 全局 prompt 历史
- 子代理 side chain 文件
- 动态组装 state & persistence

**设计哲学**：
- 轻量持久化是 AIGC CLI 工具通用最佳实践
- 语义摘要 + 局部上下文加载 → 显著降低 token 成本
- 用户态存储隔离 → 提升隐私安全性
- 可重放的会话日志结构 → 便于质量评估和 Prompt 调优

### 1.3 Claude-Mem（社区开源项目）

**GitHub**: `thedotmack/claude-mem`（登顶 GitHub Trending）

**核心设计**：
- 存储层：SQLite 3
- 三层渐进式披露（Progressive Disclosure）：
  1. **会话级摘要** — 快速了解上次做了什么
  2. **项目级记忆** — 跨会话的关键决策和规范
  3. **详细日志** — 完整的工具调用和对话记录
- LLM 驱动的压缩：智能提取关键信息，Token 成本降低 95%
- 完全离线可用

### 1.4 Agent Memory 系统最佳实践

**记忆类型分类**（认知科学 → Agent 工程映射）：

| 记忆类型 | 人类类比 | Agent 映射 | 存储内容 | 检索方式 |
|---------|---------|-----------|---------|---------|
| **工作记忆** (Working) | 当前正在想的事 | `agent.state.context`（内存） | 当前会话上下文 | 直接访问 |
| **情景记忆** (Episodic) | "昨天和同事讨论了什么" | 历史会话消息 | 完整对话记录、工具调用 | 关键词 + 语义 |
| **语义记忆** (Semantic) | "Python 是动态语言" | 事实、偏好、知识 | 用户偏好、项目规则、学到的知识 | 语义检索 |
| **程序记忆** (Procedural) | "解决 N+1 查询的标准步骤" | 已验证的流程模式 | 决策模式、工作流模板 | 语义检索 |

**记忆生命周期**：
```
raw messages → [LLM 提取] → episodic memories → [consolidation 巩固]
                                                    ↓
                                          semantic / procedural memories
                                                    ↓
                                           [decay 衰减] → 归档或删除
```

**混合检索（Hybrid Retrieval）**：

业界共识：**BM25（关键词）+ Embedding（语义）+ RRF 融合** 是生产环境最稳定的方案。

| 检索方式 | 优势 | 劣势 | 适用场景 |
|---------|------|------|---------|
| BM25 关键词 | 精确匹配专有名词、函数名；零推理成本 | 无法理解同义词、语义 | 搜"redis"、"handleAuth" |
| Embedding 语义 | 理解意图、同义词、跨语言 | 专有名词精度低；需要 embedding 模型 | 搜"怎么处理登录失败" |
| RRF 融合 | 综合两者优势 | 实现稍复杂 | 通用场景 |

**RRF（Reciprocal Rank Fusion）算法**：

```
RRF_score(d) = Σ 1 / (k + rank_i(d))
```
- `k`：平滑参数（通常取 60）
- `rank_i(d)`：文档 d 在第 i 个检索系统中的排名
- 不关心原始得分，只关心排名，对不同检索系统天然兼容

### 1.5 zvec（阿里开源嵌入式向量数据库）

**定位**：向量数据库界的 SQLite — 进程内运行，不启动额外服务

**GitHub**: `alibaba/zvec`，11.2K Stars，Apache 2.0 协议

**核心特性**：
- `pip install zvec` 即用，无需 Docker、无需配置文件、无需独立服务
- C++ 底层 + Python SDK，毫秒级检索
- 阿里内部生产环境验证（推荐系统、搜索、内容理解）
- DiskANN 索引：大规模向量数据可放在磁盘，降低内存占用

**v0.5.0（2026.06）关键能力**：
- **内置 FTS 全文搜索**：直接在字段上建 FTS 索引，不需要外接 Elasticsearch
- **内置混合检索（Hybrid Retrieval）**：`MultiQuery` 同时做向量检索 + 全文搜索 + 标量过滤
- 多语言 SDK：Python / Node.js / Go / Rust / Dart

**Python API 示例**：
```python
import zvec

# 创建 collection
schema = zvec.CollectionSchema(
    name="memories",
    vectors=zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, 384),
)
collection = zvec.create_and_open(path="./data/zvec", schema=schema)

# 插入文档（带文本字段，可建 FTS 索引）
collection.insert([
    zvec.Doc(id="mem_1", vectors={"embedding": [0.1, 0.2, ...]},
             fields={"content": "用户偏好使用 uv 管理 Python 依赖", "type": "semantic"}),
])

# 混合检索：向量相似 + 关键词 + 类型过滤
results = collection.query(
    zvec.MultiQuery(
        vector_query=zvec.VectorQuery("embedding", vector=query_embedding, topk=20),
        fts_query=zvec.FTSQuery("content", query="uv AND Python", topk=20),
        filter_expr='type in ("semantic", "procedural")',
    ),
    topk=10
)
```

### 1.6 Embedding 方案对比

| 方案 | 依赖 | 模型大小 | 速度 | 中文支持 | 适用场景 |
|------|------|---------|------|---------|---------|
| **DeepSeek API** | 无（已有 API Key） | 云端 | 中 | 好 | 首选，零额外依赖 |
| **FastEmbed** | `pip install fastembed` | ~100MB | 快（ONNX） | 好（BGE-small-zh） | 本地离线，轻量 |
| **sentence-transformers** | `pip install sentence-transformers` | ~100MB | 中 | 好 | 模型选择多，但依赖 PyTorch（~2GB） |
| **ONNX Runtime** | `pip install onnxruntime` | ~100MB | 最快 | 取决于模型 | 极致性能，需手动导出模型 |

**推荐策略**：**FastEmbed 为默认（本地离线，CPU 优先），DeepSeek API 为可选**

```python
# 默认：FastEmbed 本地（CPU 优化，ONNX 推理，无需网络）
from fastembed import TextEmbedding
model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")  # 中文优化，384维
embedding = list(model.embed([text]))[0]

# 可选：DeepSeek API Embedding（云端，需网络）
from openai import OpenAI
client = OpenAI(api_key=config.deepseek_api_key, base_url=config.deepseek_base_url)
response = client.embeddings.create(model="deepseek-embedding", input=text)
embedding = response.data[0].embedding
```

## 二、推荐方案：SQLite + zvec 双层存储

### 2.1 数据目录

```
data/                              # 项目数据目录
├── agent.db                       # SQLite 主数据库（会话、消息、记忆元数据）
├── zvec/                          # zvec 向量数据库（embedding + FTS + 混合检索）
├── tasks/                         # 异步任务 JSON 文件（已有，从 .trae/tasks/ 迁移）
└── logs/                          # JSONL 审计日志（可选）
```

### 2.2 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                         Agent 运行时                               │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐            │
│  │ agent.py │  │ tools.py │  │ context compression   │            │
│  │ (Agent)  │  │ (Toolkit)│  │ (AgentScope 内置)     │            │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘            │
│       │              │                   │                        │
│       └──────────────┼───────────────────┘                        │
│                      │                                            │
│         ┌────────────┼────────────┐                               │
│         │            │            │                               │
│  ┌──────▼─────┐ ┌────▼─────┐ ┌───▼──────────┐                    │
│  │SessionStore│ │MemoryStore│ │HybridRetriever│  ← 新增模块       │
│  │(会话/消息)  │ │(记忆管理)  │ │(混合检索)     │                    │
│  └──────┬─────┘ └────┬─────┘ └───┬──────────┘                    │
│         │            │            │                               │
│         │            │            │                               │
│  ┌──────▼─────┐ ┌────▼──────────┐                                │
│  │  SQLite    │ │  zvec         │                                │
│  │  (结构化)   │ │  (向量+FTS)   │  ← zvec 内置 FTS + 混合检索     │
│  └────────────┘ └───────────────┘                                │
│                                                                   │
│  data/                                                            │
│  ├── agent.db         ← SQLite（会话、消息、记忆元数据）            │
│  ├── zvec/            ← zvec 向量存储（embedding + FTS 索引）      │
│  ├── tasks/           ← 异步任务                                  │
│  └── logs/            ← 审计日志                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 存储分层与职责

| 层级 | 存储介质 | 职责 | 数据内容 |
|------|---------|------|---------|
| **会话存储** | SQLite | 会话和消息的持久化 | 会话元数据、完整消息历史、工具调用日志 |
| **记忆存储** | SQLite + zvec | 跨会话长期记忆 | SQLite 存元数据（content, type, importance）；zvec 存向量 + FTS 索引 |
| **向量存储** | zvec | 语义检索 + 关键词检索 | embedding 向量 + 全文搜索索引 |
| **任务存储** | JSON 文件 | 异步任务（已有） | 任务状态和结果 |
| **审计日志** | JSONL | 可回放日志（可选） | 追加式完整对话记录 |

## 三、SQLite Schema 设计

### 3.1 会话 & 消息（会话存储）

```sql
-- 会话表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,                    -- UUID
    name TEXT NOT NULL,                     -- 会话名称
    model TEXT,                             -- 使用的模型
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT DEFAULT 'active',           -- active | archived
    summary TEXT,                            -- 上下文压缩摘要
    message_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0
);

-- 消息表
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,                     -- user | assistant | system | tool
    content TEXT NOT NULL,
    tool_calls TEXT,                        -- JSON: 工具调用详情
    tool_call_id TEXT,                      -- 工具调用关联 ID
    token_count INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- 工具调用日志表
CREATE TABLE tool_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    tool_input TEXT,                        -- JSON
    tool_output TEXT,                       -- JSON
    status TEXT NOT NULL,                   -- success | error | running
    duration_ms INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

-- 索引
CREATE INDEX idx_messages_session ON messages(session_id, created_at);
CREATE INDEX idx_tool_logs_session ON tool_logs(session_id, created_at);
CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC);
```

### 3.2 记忆系统（记忆存储）

```sql
-- 记忆表（统一存储三种记忆类型）
CREATE TABLE memories (
    id TEXT PRIMARY KEY,                    -- UUID
    type TEXT NOT NULL,                     -- episodic | semantic | procedural
    content TEXT NOT NULL,                  -- 记忆内容
    source_session_id TEXT,                 -- 来源会话（episodic 关联）
    metadata TEXT,                          -- JSON: {tags, confidence, ...}
    importance REAL DEFAULT 0.5,           -- 重要性 0.0-1.0
    access_count INTEGER DEFAULT 0,         -- 被检索次数
    last_accessed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_session_id) REFERENCES sessions(id)
);

-- 记忆索引
CREATE INDEX idx_memories_type ON memories(type, created_at);
CREATE INDEX idx_memories_importance ON memories(importance DESC);
CREATE INDEX idx_memories_accessed ON memories(last_accessed_at);
```

**注意**：关键词检索（FTS）由 zvec 内置处理，不在 SQLite 中建 FTS5 虚拟表。SQLite 仅存储记忆的结构化元数据。

**记忆类型说明**：

| 类型 | 来源 | 内容示例 | 生命周期 |
|------|------|---------|---------|
| `episodic` | 会话压缩后自动提取 | "用户讨论了 Redis 缓存策略，决定使用 LRU" | 短期，可升级为 semantic |
| `semantic` | 手动添加 / episodic 升级 | "用户偏好使用 uv 管理 Python 依赖" | 长期，直到被更新 |
| `procedural` | 多次验证后从 episodic 升格 | "修复 N+1 查询的标准步骤：1. 检查 ORM 日志 2. ..." | 长期，反复验证 |

### 3.3 WAL 模式配置

```sql
PRAGMA journal_mode = WAL;       -- 写前日志，支持并发读
PRAGMA synchronous = NORMAL;     -- 平衡安全性与性能
PRAGMA foreign_keys = ON;        -- 外键约束
PRAGMA busy_timeout = 5000;      -- 5秒超时
```

## 四、混合检索设计

### 4.1 检索架构（zvec 内置 MultiQuery）

zvec v0.5.0 内置了混合检索，一行 `MultiQuery` 同时完成向量检索 + 全文搜索 + 标量过滤，无需手动 RRF 融合。

```
用户查询 "之前怎么处理 Redis 连接的？"
        │
        ▼
┌──────────────────────────────────────────┐
│           HybridRetriever                 │
│                                           │
│  ┌────────────────────────────────────┐   │
│  │         zvec MultiQuery             │   │
│  │                                     │   │
│  │  VectorQuery("embedding", query)    │   │
│  │  + FTSQuery("content", "Redis 连接") │   │
│  │  + filter: type in ("semantic",     │   │
│  │             "procedural")           │   │
│  │                                     │   │
│  │  → zvec 内部融合排序 → Top-K         │   │
│  └────────────────────────────────────┘   │
│                                           │
│  结果：融合排序后的记忆列表                  │
└──────────────────────────────────────────┘
```

### 4.2 检索组件

**语义检索（Embedding）**：
- DeepSeek API Embedding（默认，零额外依赖）
- 或 FastEmbed 本地模型（离线备选）
- 将查询文本转为向量，通过 zvec `VectorQuery` 检索

**关键词检索（FTS）**：
- zvec 内置 FTS 索引，在 `content` 字段上建索引
- 支持布尔表达式：`"Redis AND 连接"`、`"uv OR pip"`
- 与向量检索在同一个 `MultiQuery` 中完成

**zvec 混合检索代码**：
```python
def search(self, query: str, top_k: int = 10,
           memory_types: list[str] | None = None) -> list[dict]:
    """混合检索：向量 + 关键词 + 类型过滤。"""
    # 1. 生成查询向量
    embedding = self._embed(query)

    # 2. 构建 zvec MultiQuery
    queries = [
        zvec.VectorQuery("embedding", vector=embedding, topk=top_k * 2),
        zvec.FTSQuery("content", query=query, topk=top_k * 2),
    ]

    # 3. 类型过滤（可选）
    filter_expr = None
    if memory_types:
        types_str = ", ".join(f'"{t}"' for t in memory_types)
        filter_expr = f'type in ({types_str})'

    # 4. 执行混合检索，zvec 内部自动融合排序
    results = self.collection.query(
        zvec.MultiQuery(*queries, filter_expr=filter_expr),
        topk=top_k,
    )

    # 5. 从 SQLite 补充元数据
    return [self._enrich(r) for r in results]
```

**与手动 RRF 融合的对比**：

| 维度 | 手动 RRF（BM25 + Chroma） | zvec MultiQuery |
|------|--------------------------|-----------------|
| 代码复杂度 | 高（需维护两套索引 + 融合逻辑） | 低（一行 MultiQuery） |
| 性能 | 两次检索 + Python 融合 | 一次调用，C++ 内部融合 |
| 一致性 | 需手动保证两套索引同步 | zvec 自动保证 |
| 维护成本 | 高 | 低 |

### 4.3 Embedding 生成策略

```python
class EmbeddingProvider:
    """统一的 embedding 接口，支持多种后端。"""

    def __init__(self, config: Config) -> None:
        self._backend = config.embedding_backend  # "deepseek" | "fastembed"
        if self._backend == "deepseek":
            self._client = OpenAI(
                api_key=config.deepseek_api_key,
                base_url=config.deepseek_base_url,
            )
            self._model = "deepseek-embedding"
        elif self._backend == "fastembed":
            from fastembed import TextEmbedding
            self._model = TextEmbedding(
                model_name=config.embedding_model_name,
            )

    def embed(self, text: str) -> list[float]:
        """生成单个文本的 embedding。"""
        if self._backend == "deepseek":
            resp = self._client.embeddings.create(
                model=self._model, input=text,
            )
            return resp.data[0].embedding
        elif self._backend == "fastembed":
            return list(self._model.embed([text]))[0].tolist()

### 4.4 记忆生命周期

```
┌──────────────────────────────────────────────────────────────┐
│                      记忆生命周期                              │
│                                                               │
│  会话消息 ──→ [LLM 提取] ──→ episodic memory ──→ 写入 SQLite  │
│                                   │         ──→ 写入 Chroma   │
│                                   │                           │
│                     [consolidation 巩固]                      │
│                     多次引用/高重要性                          │
│                                   │                           │
│                                   ▼                           │
│                          semantic / procedural memory         │
│                                   │                           │
│                                   │                           │
│                     [decay 衰减]                              │
│                     低重要性 + 长时间未访问                     │
│                                   │                           │
│                                   ▼                           │
│                              归档 / 删除                       │
└──────────────────────────────────────────────────────────────┘
```

**记忆提取（Memory Extraction）**：
- 触发时机：会话压缩时（`compress_context` 触发后）
- 由 LLM 从被压缩的消息中提取关键信息
- 生成 1-3 条 episodic memory
- 可配置是否启用（`memory_extraction_enabled`）

**记忆巩固（Consolidation）**：
- 触发时机：episodic memory 被多次检索（`access_count >= 3`）
- 将 episodic 升级为 semantic 或 procedural
- 合并重复记忆

**记忆衰减（Decay）**：
- 触发时机：定时清理（daily）
- 条件：`importance < 0.3` AND `last_accessed_at > 30 days ago`
- 归档到 `memories_archive` 表或直接删除

## 五、模块设计

### 5.1 新增模块

#### `app/store.py` — 会话存储

```python
class SessionStore:
    """SQLite-backed session and message persistence."""

    def __init__(self, db_path: str) -> None: ...

    # ---- Session CRUD ----
    def create_session(self, name: str | None = None) -> str: ...
    def list_sessions(self, status: str = "active", limit: int = 50) -> list[dict]: ...
    def get_session(self, session_id: str) -> dict | None: ...
    def delete_session(self, session_id: str) -> bool: ...
    def cleanup_old_sessions(self, max_count: int, max_age_days: int) -> int: ...

    # ---- Message CRUD ----
    def save_message(self, session_id: str, role: str, content: str,
                     tool_calls: list | None = None,
                     tool_call_id: str | None = None,
                     token_count: int = 0) -> int: ...
    def save_tool_log(self, session_id: str, message_id: int,
                      tool_name: str, tool_input: str,
                      tool_output: str, status: str,
                      duration_ms: int = 0) -> int: ...
    def get_messages(self, session_id: str, limit: int | None = None,
                     offset: int = 0) -> list[dict]: ...

    # ---- Session Recovery ----
    def load_session(self, session_id: str, agent: "Agent") -> bool: ...
    def resume_last_session(self, agent: "Agent") -> str | None: ...

    # ---- Summary ----
    def save_summary(self, session_id: str, summary: str) -> None: ...
    def get_summary(self, session_id: str) -> str | None: ...
```

#### `app/memory.py` — 记忆存储与管理

```python
class MemoryStore:
    """Cross-session memory with CRUD and lifecycle management."""

    def __init__(self, db_path: str, zvec_path: str,
                 embedding: "EmbeddingProvider") -> None: ...

    # ---- Memory CRUD ----
    def add_memory(self, type: str, content: str,
                   source_session_id: str | None = None,
                   metadata: dict | None = None,
                   importance: float = 0.5) -> str:
        """添加记忆：写入 SQLite 元数据 + zvec 向量索引。"""
        ...

    def get_memory(self, memory_id: str) -> dict | None: ...
    def update_memory(self, memory_id: str, **kwargs) -> bool: ...
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆：从 SQLite 和 zvec 同时删除。"""
        ...

    def list_memories(self, type: str | None = None,
                      limit: int = 50) -> list[dict]: ...

    # ---- Memory Lifecycle ----
    def extract_from_session(self, session_id: str,
                             messages: list[dict]) -> list[str]:
        """从会话消息中提取记忆（调用 LLM）。"""
        ...

    def consolidate(self) -> int:
        """巩固记忆：将高频 episodic 升级为 semantic/procedural。"""
        ...

    def decay(self, max_age_days: int = 30,
              importance_threshold: float = 0.3) -> int:
        """衰减低重要性且长期未访问的记忆。"""
        ...

    # ---- Sync with zvec ----
    def sync_to_zvec(self, memory_id: str) -> None:
        """将记忆写入 zvec（embedding + FTS 索引）。"""
        ...

    def rebuild_index(self) -> None:
        """从 SQLite 全量重建 zvec 索引（启动时调用）。"""
        ...
```

#### `app/retriever.py` — 混合检索

```python
class HybridRetriever:
    """基于 zvec MultiQuery 的混合检索（向量 + FTS + 过滤）。"""

    def __init__(self, zvec_path: str,
                 embedding: "EmbeddingProvider") -> None: ...

    def search(self, query: str, top_k: int = 10,
               memory_types: list[str] | None = None,
               min_importance: float = 0.0) -> list[dict]:
        """混合检索：zvec MultiQuery 自动融合向量 + 关键词 + 类型过滤。"""
        ...
```

#### `app/memory_tool.py` — 记忆工具（Agent 可调用）

```python
# 作为 FunctionTool 注册到 Toolkit，Agent 可以直接调用

async def search_memory(query: str, memory_type: str = "all",
                        top_k: int = 5) -> ToolChunk:
    """搜索记忆（混合检索）。

    Args:
        query: 搜索查询
        memory_type: 记忆类型过滤（episodic | semantic | procedural | all）
        top_k: 返回结果数量
    """
    ...

async def add_memory(content: str, memory_type: str = "semantic",
                     importance: float = 0.5) -> ToolChunk:
    """手动添加一条记忆。"""
    ...

async def list_memories(memory_type: str = "all",
                        limit: int = 20) -> ToolChunk:
    """列出记忆。"""
    ...

async def forget_memory(memory_id: str) -> ToolChunk:
    """删除一条记忆。"""
    ...
```

### 5.2 修改现有模块

#### `app/agent.py`

```python
async def build_agent(config: Config, toolkit: Toolkit,
                      store: SessionStore | None = None,
                      memory: MemoryStore | None = None) -> Agent:
    """构建 Agent，可选注入 SessionStore 和 MemoryStore。"""
    ...
```

#### `app/config.py`

```python
@dataclass
class Config:
    # ... existing fields ...

    # ---- 持久化配置 ----
    data_dir: str = "data"
    """数据目录"""

    db_path: str = "data/agent.db"
    """SQLite 数据库路径"""

    zvec_path: str = "data/zvec"
    """zvec 向量数据库路径"""

    session_max_count: int = 50
    """最大保留会话数（参考 Codex）"""

    session_max_age_days: int = 30
    """会话最大保留天数（参考 Codex）"""

    persistence_mode: str = "save-all"
    """持久化模式：save-all | chat-only | none（参考 Codex）"""

    # ---- 记忆配置 ----
    memory_enabled: bool = True
    """是否启用记忆系统"""

    memory_extraction_enabled: bool = True
    """是否在压缩时自动提取记忆"""

    memory_consolidation_threshold: int = 3
    """episodic 被访问多少次后升格为 semantic"""

    memory_decay_days: int = 30
    """记忆衰减天数"""

    # ---- Embedding 配置 ----
    embedding_backend: str = "fastembed"
    """Embedding 后端：fastembed | deepseek"""

    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    """FastEmbed 模型名称（仅 embedding_backend=fastembed 时生效）"""
```

#### `app/cli.py`

- 启动时展示会话管理菜单（新建/恢复/删除）
- 每次交互后自动保存消息到 SQLite
- 压缩触发后自动提取记忆
- 退出时清理过期会话和记忆
- 启动时调用 `memory.rebuild_index()` 同步 Chroma

#### `app/service.py`

新增 API 端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/sessions` | 列出会话 |
| `POST` | `/api/sessions` | 创建会话 |
| `GET` | `/api/sessions/{id}` | 获取会话详情 |
| `GET` | `/api/sessions/{id}/messages` | 获取会话消息 |
| `DELETE` | `/api/sessions/{id}` | 删除会话 |
| `POST` | `/api/sessions/{id}/resume` | 恢复会话 |
| `GET` | `/api/memories` | 列出记忆 |
| `POST` | `/api/memories` | 添加记忆 |
| `GET` | `/api/memories/search?q=...` | 搜索记忆（混合检索） |
| `DELETE` | `/api/memories/{id}` | 删除记忆 |

### 5.3 与现有系统的关系

| 现有系统 | 关系 | 说明 |
|---------|------|------|
| `agent.state.context`（内存） | 运行时镜像 | SQLite 是持久化副本，内存是运行时工作集 |
| `compress_context()`（压缩） | 互补 + 触发 | 压缩前完整数据写入 SQLite；压缩后触发记忆提取 |
| `agent.state.summary`（摘要） | 持久化 | 摘要存入 `sessions.summary` |
| `TaskManager`（任务） | 迁移 | 从 `.trae/tasks/` 迁移到 `data/tasks/` |
| `SubagentRunner`（子代理） | 关联 | 子代理消息写入同一 SQLite（关联 session_id） |

## 六、依赖分析

**新增依赖**：

| 包 | 用途 | 类型 | 备注 |
|----|------|------|------|
| `zvec` | 嵌入式向量数据库（向量 + FTS + 混合检索） | 核心 | `pip install zvec`，Apache 2.0 |
| `fastembed` | 本地 embedding 模型（ONNX，CPU 优化，默认） | 核心 | `pip install fastembed`，~100MB |

**已有依赖**（无需新增）：
- `sqlite3`（Python 标准库）
- `openai`（已有，用于 DeepSeek API — 包括 Chat + Embedding）
- `pyyaml`（已有）
- `agentscope`（已有）

**依赖对比**：

| 方案 | 新增包 | 安装大小 | 是否需要额外服务 | 默认 |
|------|--------|---------|----------------|------|
| FastEmbed（本地） | `zvec` + `fastembed` | ~110MB | 否 | 是 |
| DeepSeek API（云端） | `zvec` | ~10MB | 否（需网络） | 否 |
| Chroma + sentence-transformers | `chromadb` + `sentence-transformers` | ~2GB（含 PyTorch） | 否 | 否 |

## 七、实施计划

### Phase 1：数据目录迁移 + 核心存储层

- [ ] 将 `.trae/tasks/` 迁移到 `data/tasks/`，更新 `TaskManager`
- [ ] 创建 `app/store.py`：SQLite 初始化、建表、WAL 模式
- [ ] 实现 `SessionStore` 基础 CRUD（会话 + 消息 + 工具日志）
- [ ] 编写测试 `tests/test_store.py`（10+ 用例）

### Phase 2：Embedding 层 + 记忆存储层

- [ ] 创建 `app/embedding.py`：`EmbeddingProvider` 类（DeepSeek API + FastEmbed 双后端）
- [ ] 创建 `app/memory.py`：`MemoryStore` 类
- [ ] 实现记忆 CRUD（add / get / update / delete / list）
- [ ] 实现 zvec 集成（init / sync_to_zvec / rebuild_index）
- [ ] 实现记忆提取（LLM 从压缩消息中提取）
- [ ] 实现记忆巩固（episodic → semantic）
- [ ] 实现记忆衰减（过期清理）
- [ ] 编写测试 `tests/test_embedding.py`（4+ 用例）+ `tests/test_memory.py`（10+ 用例）

### Phase 3：混合检索

- [ ] 创建 `app/retriever.py`：`HybridRetriever` 类
- [ ] 实现 zvec MultiQuery（向量 + FTS + 类型过滤）
- [ ] 实现结果增强（从 SQLite 补充元数据）
- [ ] 编写测试 `tests/test_retriever.py`（6+ 用例）

### Phase 4：工具集成

- [ ] 创建 `app/memory_tool.py`：`search_memory` / `add_memory` / `list_memories` / `forget_memory`
- [ ] 注册到 Toolkit
- [ ] 编写测试

### Phase 5：Agent 集成

- [ ] 修改 `app/agent.py`，注入 `SessionStore` + `MemoryStore`
- [ ] 实现消息钩子：每次交互自动写入 SQLite
- [ ] 实现会话恢复：从 SQLite 加载历史到 `agent.state.context`
- [ ] 与 `compress_context()` 集成：压缩后自动提取记忆

### Phase 6：CLI + API + 文档

- [ ] 修改 `app/cli.py`：会话管理菜单 + 记忆操作
- [ ] 修改 `app/service.py`：新增 10 个 API 端点
- [ ] 更新 `app/config.py`：新增所有配置项
- [ ] 更新 `README.md` + `docs/architecture.md`
- [ ] 运行全部测试，确保无回归

## 八、注意事项

1. **不破坏现有功能**：当前 `agent.state.context` 内存存储保持不变，SQLite/zvec 作为附加持久化层
2. **向后兼容**：`persistence_mode = "none"` + `memory_enabled = False` 时完全等同于现有行为
3. **zvec 零配置**：`pip install zvec` 后进程内运行，一个目录即一个数据库，不需要额外服务
4. **Embedding 默认使用 FastEmbed 本地模型**：CPU 优化，ONNX 推理，~100MB，无需网络。如需云端，切换 `embedding_backend=deepseek` 即可
5. **zvec 内置混合检索**：无需手动维护 FTS5 + Chroma 两套索引，一行 `MultiQuery` 完成向量 + 关键词 + 过滤
6. **性能**：zvec C++ 底层，毫秒级检索；DiskANN 索引支持大规模数据
7. **安全**：所有数据存储在 `data/` 目录，已在 `.gitignore` 中
8. **AgentScope 兼容**：不修改 AgentScope 内部逻辑，通过钩子模式集成
9. **记忆提取的质量依赖 LLM**：提取效果取决于 DeepSeek 模型的理解能力