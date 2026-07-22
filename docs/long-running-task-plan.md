# 长程任务能力增强计划

## 1. 概述

当前 Agent 的任务系统（TaskManager）只支持基本的异步执行和状态轮询，缺少长程任务所需的进度反馈、容错重试和任务规划能力。本计划分三期实现三个核心能力。

## 2. 当前状态

- `app/task_manager.py`：TaskRecord 有 status/result/error，无 progress；execute() 直接调 agent.reply()，无中间状态
- `app/subagent.py`：SubagentRunner 独立执行，结果以字符串返回
- `app/service.py`：任务 API 只有 submit/get/list/cancel，无 SSE 进度流
- `app/tools.py`：17 个工具，无重试逻辑
- `app/config.py`：无 retry/planning 相关配置

## 3. 设计方案

### Phase 1：进度反馈（Progress Reporting）

**TaskRecord 增强**：
```python
@dataclass
class TaskRecord:
    # ... 现有字段 ...
    progress: int = 0          # 0-100 百分比
    current_step: str = ""     # 当前步骤描述，如 "正在搜索互联网..."
    steps: list[dict] = field(default_factory=list)  # [{step, status, result}]
```

**新增 `report_progress` 工具**（Agent 可调用）：
```python
async def report_progress(
    progress: int,        # 0-100
    current_step: str,     # 当前步骤描述
    step_result: str = "", # 步骤结果
) -> AsyncGenerator[ToolChunk, None]:
    """Agent 在执行中调用，更新任务进度。"""
```

**新增 SSE 端点** `GET /api/tasks/{task_id}/stream`：
- 客户端连接后持续推送进度更新
- 事件格式：`{type: "progress", progress: 50, current_step: "..."}`
- 任务完成时发送 `{type: "done", result: "..."}`

**Web UI 增强**：
- 提交任务后显示进度条 + 当前步骤文字
- 实时更新（通过 SSE 连接）

### Phase 2：重试机制（Retry with Backoff）

**配置新增**：
```python
tool_retry_max: int = 3           # 最大重试次数
tool_retry_backoff: float = 2.0   # 指数退避因子
tool_retry_initial_delay: float = 1.0  # 初始延迟秒数
```

**重试装饰器**：
```python
@retry_on_failure(max_retries=3, backoff=2.0)
async def execute_with_retry(tool_call):
    ...
```

**可重试条件**：
- 网络超时（TimeoutError）
- API 限流（HTTP 429）
- 临时错误（ConnectionError）
- 不可重试：权限错误、参数错误、资源不存在

**日志记录**：
- 每次重试记录到 tool_logs 表
- retry_count 字段追踪重试次数

### Phase 3：任务规划（Task Planning）

**plan_task 工具**（Agent 可调用）：
```python
async def plan_task(
    goal: str,               # 任务目标
    subtasks: list[str],     # 子任务列表
) -> AsyncGenerator[ToolChunk, None]:
    """创建任务计划，将大任务分解为子任务。"""
```

**Subtask 状态机**：
```
pending → running → completed/failed
```

**执行流程**：
1. Agent 调用 `plan_task` 创建子任务列表
2. 按顺序执行每个子任务，调用 `report_progress` 更新进度
3. 子任务失败时根据策略决定：重试 / 跳过 / 中止
4. 全部完成后汇总结果

**系统提示词增强**：
```
When working on complex, multi-step tasks:
1. Use plan_task to break down the task into subtasks
2. Execute each subtask in order
3. Call report_progress after each subtask completes
4. If a subtask fails, try alternative approaches before giving up
```

## 4. 涉及文件

| 文件 | Phase | 改动 |
|------|-------|------|
| `app/config.py` | 1+2 | 新增 retry 配置项 |
| `app/task_manager.py` | 1 | TaskRecord 增加 progress/current_step/steps；execute() 支持进度回调 |
| `app/tools.py` | 1+3 | 注册 report_progress + plan_task 工具 |
| `app/service.py` | 1 | 新增 GET /api/tasks/{id}/stream SSE 端点；Web UI 显示进度条 |
| `app/retry.py` | 2 | 新增 retry_on_failure 装饰器 |
| `app/task_planner.py` | 3 | 新增 plan_task 工具 + subtask 管理 |
| `tests/test_task_api.py` | 1+2+3 | 新增测试用例 |

## 5. 实现步骤

### Phase 1：进度反馈（预计 20 分钟）
1. `config.py`：新增 retry 配置项
2. `task_manager.py`：TaskRecord 加 progress/current_step/steps 字段；execute() 注入进度回调
3. `tools.py`：新增 `report_progress` 工具
4. `service.py`：新增 SSE 端点 + Web UI 进度条
5. 测试 + 验证

### Phase 2：重试机制（预计 15 分钟）
1. `app/retry.py`：实现 retry_on_failure 装饰器
2. `tools.py`：在 build_toolkit 中包装工具
3. 测试 + 验证

### Phase 3：任务规划（预计 15 分钟）
1. `app/task_planner.py`：plan_task 工具 + subtask 管理
2. `tools.py`：注册 plan_task 工具
3. `agent.py`：系统提示词更新
4. 测试 + 验证

## 6. 测试用例

| Phase | # | 场景 | 预期 |
|-------|---|------|------|
| 1 | 1 | 提交任务后通过 SSE 接收进度 | 收到 progress 事件，进度值递增 |
| 1 | 2 | Agent 调用 report_progress | 进度更新成功，TaskRecord 字段正确 |
| 1 | 3 | Web UI 显示进度条 | 提交任务后出现进度条，实时更新 |
| 2 | 4 | 工具调用失败自动重试 | 重试 3 次后成功或失败 |
| 2 | 5 | 不可重试错误直接失败 | 权限错误不重试，立即返回失败 |
| 3 | 6 | plan_task 创建子任务 | 返回子任务列表，状态均为 pending |
| 3 | 7 | 子任务按序执行 | 完成一个后自动开始下一个 |

## 7. 验证

```bash
uv run pytest tests/test_task_api.py -v -x -s
curl -N http://localhost:8000/api/tasks/{task_id}/stream  # SSE 进度流
curl -X POST http://localhost:8000/api/tasks -H "Content-Type: application/json" -d '{"content":"搜索 Python 最新版本并总结"}'
```
__tr_native_ec=$?; pwd -P >| '/var/folders/k9/0952msvs7n5djrc0lc_x78qw0000gn/T/trae-agent-toolhost-501/jobs/job-e295651480db4b34bf0253b042e7f72d/cwd.txt'; exit "$__tr_native_ec"