# Context Compaction（上下文压缩）实现方案

## Summary

为 Agent 添加上下文压缩能力，当 token 达到 20K 时发出警告，达到 40% DeepSeek 上下文窗口（51.2K）时自动触发压缩。AgentScope 2.0 已内置完整的 `compress_context()` 机制，本方案基于此扩展监控和流式可见性。

---

## Phase 1 探索结论

### AgentScope 内置压缩机制

AgentScope 2.0 的 `Agent` 类已经实现了完整的上下文压缩：

1. **自动触发**：每次 reasoning 前自动调用 `compress_context()`（`_agent.py:762`）
2. **Token 计数**：通过 `model.count_tokens()` 精确计算（非估算）
3. **结构化压缩**：使用 `SummarySchema` 生成结构化摘要，包含：
   - `task_overview` — 用户核心请求和成功标准
   - `current_state` — 已完成的工作、文件变更
   - `important_discoveries` — 技术约束、决策、错误修复
   - `next_steps` — 待完成的具体行动
   - `context_to_preserve` — 用户偏好、领域细节、承诺
4. **配置驱动**：`ContextConfig` 控制所有行为
   - `trigger_ratio`: 触发阈值（默认 0.8 = 80%）
   - `reserve_ratio`: 保留最近消息比例（默认 0.1 = 10%）
   - `compression_prompt`: 压缩引导 prompt
   - `summary_template`: 摘要展示模板
5. **溢出保护**：上下文溢出时自动移除最旧消息重试
6. **中断保护**：`asyncio.shield` 保护状态更新不被中断

### 当前项目状态

- `app/agent.py`: `build_agent()` 创建 Agent，未传递 `ContextConfig`
- `app/cli.py`: 流式事件循环，未检测压缩状态
- `app/service.py`: SSE 流式端点，未发送压缩相关事件
- `app/tools.py`: 未注册压缩相关工具

---

## Proposed Changes

### 1. `app/config.py` — 新增压缩配置

**What**: 添加 `compaction_trigger_ratio` 和 `compaction_warning_tokens` 配置项

**Why**: 使用户可配置触发阈值，默认 0.4（40% = 51.2K for DeepSeek 128K）

**How**:
```python
@dataclass
class Config:
    # ... existing fields ...
    
    compaction_trigger_ratio: float = 0.4
    """触发压缩的上下文占比（0.4 = 40% of 128K = 51.2K tokens）"""
    
    compaction_warning_tokens: int = 20000
    """发出警告的 token 阈值"""
```

在 `load_config()` 中读取 `COMPACTION_TRIGGER_RATIO` 和 `COMPACTION_WARNING_TOKENS` 环境变量。

### 2. `app/agent.py` — 传递 ContextConfig

**What**: 在创建 Agent 时传递 `ContextConfig(trigger_ratio=config.compaction_trigger_ratio)`

**Why**: 覆盖默认的 0.8 触发比，改为 0.4（40%）

**How**:
```python
from agentscope.agent._config import ContextConfig

async def build_agent(config: Config, toolkit: Toolkit) -> Agent:
    return Agent(
        # ... existing params ...
        context_config=ContextConfig(
            trigger_ratio=config.compaction_trigger_ratio,
        ),
    )
```

### 3. `app/compaction.py` — 新建压缩监控模块

**What**: 创建 `context_status` FunctionTool，提供上下文状态查询和手动压缩触发

**Why**: 
- Agent 可主动调用检查 token 使用量
- 用户可手动触发压缩
- 在流式输出中展示压缩进度

**How**:
```python
# app/compaction.py

async def context_status(
    agent: Agent,
    action: str = "check",
) -> AsyncGenerator[ToolChunk, None]:
    """Check context token usage or trigger manual compaction.
    
    Args:
        agent: The Agent instance (injected)
        action: "check" to view status, "compact" to force compaction
    """
    # 获取当前 token 估算
    kwargs = await agent._prepare_model_input()
    estimated = await agent.model.count_tokens(**kwargs)
    context_size = agent.model.context_size
    usage_pct = estimated / context_size * 100
    
    if action == "check":
        level = "normal"
        if estimated >= WARNING_THRESHOLD:
            level = "warning"
        if estimated >= context_size * TRIGGER_RATIO:
            level = "critical"
        
        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[TextBlock(text=f"Token usage: {estimated:,} / {context_size:,} ({usage_pct:.1f}%) [{level}]")],
        )
    
    elif action == "compact":
        # 强制触发压缩
        await agent.compress_context()
        # 重新计算
        kwargs = await agent._prepare_model_input()
        new_estimated = await agent.model.count_tokens(**kwargs)
        yield ToolChunk(
            state=ToolResultState.SUCCESS,
            content=[TextBlock(
                text=f"Compaction complete: {estimated:,} → {new_estimated:,} tokens "
                     f"({(1 - new_estimated/estimated)*100:.1f}% reduction)"
            )],
        )
```

### 4. `app/tools.py` — 注册 context_status 工具

**What**: 将 `context_status` 注册到 BUILTIN_TOOLS

**Why**: Agent 可调用此工具检查上下文状态

**How**: 在 `BUILTIN_TOOLS` 列表中添加 `FunctionTool(context_status)`。注意：`context_status` 需要 agent 引用，使用闭包或工厂函数注入。

### 5. `app/cli.py` — 流式输出中展示压缩过程

**What**: 在流式事件循环中检测 `self.state.summary` 的变化，展示压缩进度

**Why**: 用户需要看到压缩何时发生、效果如何

**How**: 在 `run_cli()` 的事件循环中，添加 `_check_compaction()` 辅助函数：
```python
_last_summary = None

async def _check_compaction(agent) -> str | None:
    nonlocal _last_summary
    current = agent.state.summary
    if current != _last_summary:
        _last_summary = current
        if current:
            return f"  [Compaction] Context compressed, summary updated"
    return None
```

在每个事件处理周期调用此函数，如有变化则输出。

### 6. `app/service.py` — SSE 流中添加压缩事件

**What**: 在 SSE 流式响应中发送 `compaction` 类型事件

**Why**: Web UI 需要展示压缩状态

**How**: 在 `chat_stream` 的 `generate()` 中，每个事件后检查 `agent.state.summary` 是否变化，发送：
```python
yield _sse({
    "type": "compaction",
    "status": "completed",
    "summary": "Context compressed",
})
```

### 7. `tests/test_compaction.py` — 新增测试

**What**: 测试压缩模块的各个功能

**Why**: 确保压缩逻辑正确

**测试用例**:
1. `test_context_config_has_correct_trigger_ratio` — 验证 ContextConfig 配置正确
2. `test_context_status_check` — 验证 context_status("check") 返回正确状态
3. `test_agent_has_compress_context` — 验证 Agent 有 compress_context 方法
4. `test_compaction_trigger_ratio_default` — 验证默认 trigger_ratio=0.4

---

## Assumptions & Decisions

1. **利用 AgentScope 内置机制**：不重新实现压缩引擎，只配置和扩展
2. **trigger_ratio=0.4**：40% of 128K = 51.2K，满足用户需求
3. **warning 在 20K**：通过 context_status 工具实现，AgentScope 内置机制不区分 warning/critical
4. **压缩过程流式可见**：通过检测 `agent.state.summary` 变化实现，而非拦截压缩内部事件
5. **DeepSeek context_size 假设为 128K**：由 `DeepSeekChatModel.context_size` 属性提供

## Verification

1. `uv run pytest tests/ -v` — 所有测试通过
2. `uv run python -c "from app.agent import build_agent; ..."` — 验证 Agent 创建时 ContextConfig 正确
3. 手动运行 CLI 长对话，观察压缩触发