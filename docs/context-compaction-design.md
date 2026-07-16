# Context Compaction（上下文压缩）设计方案

## 1. 行业调研

### 1.1 Anthropic 的注意力预算理论

Anthropic 在 "Effective Context Engineering for AI Agents" 中提出核心观点：

> "Context must be treated as a finite resource with diminishing marginal returns. 
> Like humans, who have limited working memory capacity, LLMs have an 'attention budget'."

**关键结论**：
- 上下文窗口扩大 ≠ 能力等比例提升。超过阈值后，上下文越长，有效信息密度越低
- 目标是找到「最小高信噪比 token 集」
- System prompt 应在 Goldilocks Zone：具体到足以指导行为，灵活到允许模型自主判断

### 1.2 Claude Code 的 Compaction 机制

Claude Code 的 compaction 是业界最成熟的实现：

**触发条件**：上下文接近窗口上限时自动触发（也可手动 `/compact`）

**压缩过程**：
1. Fork 一个子调用，把完整对话历史喂给模型
2. 加上 "summarize this conversation" 指令
3. 命中 prompt cache，只需 1/10 价格
4. 生成结构化摘要，替换原有对话历史

**压缩效果**：平均压缩到原始对话的 **12%**（10K tokens → 1.2K tokens）

**保留内容**：
- 用户请求和意图
- 关键技术概念
- 检查和修改过的文件（含重要代码片段）
- 遇到的错误和修复方式
- 待处理任务
- 当前工作进度

**丢弃内容**：
- 完整工具输出
- 中间推理过程
- 精确代码内容（仅保留"重要片段"）

**Compaction 后自动恢复**（从磁盘重新注入）：
- System prompt
- 项目根 CLAUDE.md 和 unscoped rules
- Auto memory (MEMORY.md)
- MCP 工具名列表

### 1.3 Cursor 的 Self-Summarization

Cursor 将压缩能力作为模型训练目标：
- 压缩 prompt 仅需 "Please summarize the conversation"（而非数千 token 的精心设计）
- 输出压缩大小平均 ~1000 token（vs baseline 的 >5000 token）
- 压缩错误率降低 50%
- 复用 KV cache

### 1.4 关键设计原则总结

| 原则 | 说明 |
|------|------|
| 注意力预算 | 上下文是有限资源，需主动管理 |
| 结构化摘要 | 不是简单截断，而是理解后重新组织 |
| 保留关键信息 | 意图、决策、文件、错误、进度 |
| 丢弃冗余 | 工具输出、中间推理、精确代码 |
| 缓存复用 | 尽可能命中 prompt cache |
| 进度可见 | 压缩过程应对用户可见 |

---

## 2. 本项目设计方案

### 2.1 触发阈值

DeepSeek V4 Pro 上下文窗口：**128K tokens**

| 级别 | 阈值 | 行为 |
|------|------|------|
| **Warning** | 20,000 tokens | 在流式输出中显示警告 |
| **Auto-Compact** | 51,200 tokens (40%) | 自动触发压缩 |

### 2.2 实现方式

采用 **Tool + Monitor 双层架构**：

```
┌─────────────────────────────────────────────┐
│                 Agent Loop                    │
│                                              │
│  用户输入 → Token估算 → 是否超阈值？           │
│                │                              │
│         ┌─────┴─────┐                        │
│         │ 否        │ 是                      │
│         ▼           ▼                         │
│    正常回复    compact_context 工具            │
│                   │                           │
│              ┌────┴────┐                      │
│              │ Warning  │ Auto-Compact        │
│              │ (20K)    │ (40% = 51.2K)       │
│              ▼          ▼                     │
│         流式提示    1. Fork 子调用              │
│                    2. 生成结构化摘要            │
│                    3. 替换对话历史              │
│                    4. 流式展示压缩过程           │
└─────────────────────────────────────────────┘
```

### 2.3 新增模块

```
app/
├── compaction.py     # 新增：上下文压缩模块
│   ├── TokenCounter      # Token 计数器
│   ├── ContextCompactor  # 压缩执行器
│   └── compact_context() # FunctionTool 工具函数
```

### 2.4 核心接口

```python
# app/compaction.py

class TokenCounter:
    """Token 计数器，基于字符数估算（4 chars ≈ 1 token）"""
    
    def estimate(self, messages: list[dict]) -> int: ...
    def is_over_threshold(self, token_count: int) -> CompactionLevel: ...

class CompactionLevel(Enum):
    NORMAL = "normal"       # < 20K
    WARNING = "warning"     # 20K - 51.2K
    CRITICAL = "critical"   # > 51.2K (40%)

class ContextCompactor:
    """上下文压缩执行器"""
    
    async def compact(
        self,
        messages: list[dict],
        model_call: Callable,
    ) -> CompactionResult: ...
    """执行压缩，返回结构化摘要"""

@dataclass
class CompactionResult:
    summary: str              # 结构化摘要
    original_tokens: int      # 压缩前 token 数
    compacted_tokens: int     # 压缩后 token 数
    reduction_ratio: float    # 压缩比
    key_files: list[str]      # 涉及的关键文件
    pending_tasks: list[str]  # 待处理任务
```

### 2.5 压缩摘要格式

```
## Conversation Summary

### Primary Request and Intent
[用户的主要请求和意图]

### Key Decisions
- [关键决策1]
- [关键决策2]

### Files Modified/Created
- [文件路径] - [变更说明]

### Errors and Fixes
- [错误] → [修复方案]

### Current Progress
[当前进度状态]

### Pending Tasks
- [待处理任务1]
- [待处理任务2]
```

### 2.6 流式展示

压缩过程在流式输出中可见：

```
  [Compaction] analyzing context...
  [....] Token usage: 52,340 / 128,000 (40.9%)
  [....] Triggering auto-compaction...
  [....] Generating structured summary...
  [ OK ] Compaction complete: 52,340 → 6,200 tokens (88.2% reduction)
  [ .. ] 5 files referenced, 3 pending tasks preserved
```

### 2.7 改造点

| 文件 | 变更 |
|------|------|
| `app/compaction.py` | **新增** — 压缩模块 |
| `app/tools.py` | **改造** — 注册 `compact_context` 工具 |
| `app/agent.py` | **改造** — 注入压缩提示到 system prompt |
| `app/cli.py` | **改造** — 在流式循环中检测阈值并触发压缩 |
| `tests/test_compaction.py` | **新增** — 压缩模块测试 |