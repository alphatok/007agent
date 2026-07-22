# Tasks

## Phase 1: 进度反馈

- [x] Task 1.1: config.py 新增进度相关配置
  - [x] 新增 `tool_retry_max: int = 3`
  - [x] 新增 `tool_retry_backoff: float = 2.0`
  - [x] 新增 `tool_retry_initial_delay: float = 1.0`
  - **验证**: `uv run python -c "from app.config import load_config; c=load_config(); print(c.tool_retry_max)"` 输出 3

- [x] Task 1.2: task_manager.py 增强 TaskRecord
  - [x] TaskRecord 增加 `progress: int = 0` 字段
  - [x] TaskRecord 增加 `current_step: str = ""` 字段
  - [x] TaskRecord 增加 `steps: list[dict] = field(default_factory=list)` 字段
  - [x] 新增 `update_progress(task_id, progress, current_step)` 方法
  - [x] 新增 `add_step(task_id, step_desc)` 方法
  - [ ] `execute()` 方法注入进度回调函数
  - **验证**: `uv run pytest tests/test_task_api.py -v -k "progress"` 通过

- [x] Task 1.3: tools.py 新增 report_progress 工具
  - [x] 实现 `report_progress(progress: int, current_step: str, step_result: str = "")` 异步生成器
  - [x] 从 agent 上下文获取 task_id 和 task_manager
  - [x] 调用 task_manager.update_progress 更新进度
  - [x] 在 `build_toolkit()` 中注册该工具
  - **验证**: `uv run pytest tests/test_tools.py -v -k "report_progress"` 通过

- [x] Task 1.4: service.py 新增 SSE 进度端点
  - [x] 新增 `GET /api/tasks/{task_id}/stream` SSE 端点
  - [x] 使用 asyncio.Queue 在 execute() 和 SSE 之间传递进度事件
  - [x] 任务完成时发送 done 事件并关闭连接
  - **验证**: `curl -N http://localhost:8000/api/tasks/{task_id}/stream` 收到 SSE 事件

- [x] Task 1.5: Web UI 进度条
  - [x] 在 CHAT_PAGE HTML 中添加进度条 CSS 样式
  - [ ] 提交任务后创建 EventSource 连接 SSE 端点
  - [ ] 实时更新进度条宽度和文字
  - [x] 任务完成后移除进度条
  - **验证**: 浏览器提交任务后看到进度条实时更新

## Phase 2: 重试机制

- [x] Task 2.1: app/retry.py 实现重试装饰器
  - [ ] 新建 `app/retry.py`
  - [x] 实现 `retry_on_failure(max_retries, backoff, initial_delay)` 异步装饰器
  - [x] 定义可重试异常集合：`(ConnectionError, TimeoutError, OSError)`
  - [x] 实现指数退避：`delay = initial_delay * (backoff ** attempt)`
  - [ ] 记录每次重试日志
  - **验证**: `uv run python -c "from app.retry import retry_on_failure; print('OK')"` 无报错

- [x] Task 2.2: tools.py 集成重试机制
  - [x] 在 `build_toolkit()` 中包装工具执行函数
  - [ ] 为网络相关工具（web_search, web_fetch）启用重试
  - [x] 从 config 读取重试参数
  - **验证**: 模拟网络错误，工具自动重试 3 次

## Phase 3: 任务规划

- [x] Task 3.1: app/task_planner.py 实现 plan_task 工具
  - [ ] 新建 `app/task_planner.py`
  - [x] 实现 `PlanStep` 数据类：`{step_id, description, status, result}`
  - [x] 实现 `TaskPlan` 数据类：`{goal, steps, current_index}`
  - [x] 实现 `plan_task(goal, subtasks)` 工具函数（异步生成器）
  - [x] 实现 `mark_step_complete(step_id, result)` 辅助函数
  - [x] 实现 `get_next_pending_step()` 辅助函数
  - **验证**: `uv run python -c "from app.task_planner import plan_task; print('OK')"` 无报错

- [x] Task 3.2: tools.py 注册 plan_task 工具
  - [x] 在 `build_toolkit()` 中注册 plan_task 工具
  - [ ] 工具描述包含：何时使用、参数说明、返回格式
  - **验证**: `uv run pytest tests/test_tools.py -v -k "plan_task"` 通过

- [x] Task 3.3: agent.py 系统提示词更新
  - [x] 在系统提示词中添加长任务执行规范
  - [x] 内容：先规划再执行、每步报告进度、失败后尝试替代方案
  - **验证**: Agent 收到复杂任务时先调用 plan_task

## Phase 4: 断点续传

- [x] Task 4.1: app/checkpoint.py 实现检查点机制
  - [ ] 新建 `app/checkpoint.py`
  - [x] 实现 `save_checkpoint(task_id, data)` 保存到 JSON 文件
  - [x] 实现 `load_checkpoint(task_id)` 从文件恢复
  - [x] 实现 `list_checkpoints(task_id)` 列出所有检查点
  - [x] 检查点存储路径：`data/checkpoints/{task_id}.json`
  - **验证**: `uv run python -c "from app.checkpoint import save_checkpoint, load_checkpoint; print('OK')"` 无报错

- [x] Task 4.2: task_manager.py 集成检查点
  - [ ] `execute()` 中定期保存检查点（每完成一个子任务）
  - [ ] 服务启动时检查未完成任务，加载检查点
  - [x] 新增 `resume_task(task_id)` 方法
  - **验证**: 任务中断后重启服务，任务从检查点恢复

## Phase 5: 人机协作

- [x] Task 5.1: tools.py 新增 ask_user 工具
  - [x] 实现 `ask_user(question: str, options: list[str] = [])` 异步生成器
  - [x] 将任务状态设为 waiting_user
  - [x] 使用 asyncio.Event 等待用户响应
  - [x] 超时机制（默认 5 分钟）
  - **验证**: Agent 调用 ask_user 后任务暂停，等待输入

- [x] Task 5.2: service.py 新增用户响应端点
  - [x] 新增 `POST /api/tasks/{task_id}/respond` 端点
  - [x] 接收用户响应，触发 asyncio.Event
  - [x] 返回确认消息
  - **验证**: `curl -X POST .../respond -d '{"response":"SQLite"}'` 返回 200

- [x] Task 5.3: Web UI 人机协作界面
  - [x] 检测 waiting_user 状态，弹出对话框
  - [x] 显示问题和选项按钮
  - [x] 用户选择后发送 POST 请求
  - **验证**: 浏览器中看到问题弹窗，选择后继续执行

## Phase 6: 并行执行

- [x] Task 6.1: task_planner.py 并行调度
  - [x] 在 TaskPlan 中标记子任务依赖关系
  - [x] 实现 `execute_parallel(steps)` 使用 asyncio.gather
  - [x] 实现 `execute_sequential(steps)` 按序执行
  - [x] 实现 `execute_mixed(steps)` 按依赖拓扑排序执行
  - **验证**: 独立子任务同时执行，有依赖的按序执行

- [x] Task 6.2: service.py 并行任务进度汇总
  - [x] 并行执行时总体进度 = 已完成 / 总数
  - [x] 每个子任务通过 SSE 独立报告进度
  - **验证**: 提交并行任务后 SSE 收到多个子任务进度

# 测试

- [x] Task T.1: 新增测试用例
  - [x] test_task_api.py: 进度更新、SSE 连接、检查点保存/恢复
  - [x] test_tools.py: report_progress、plan_task、ask_user 工具注册
  - [x] test_retry.py: 重试装饰器、可重试/不可重试分类
  - [x] test_checkpoint.py: 保存/恢复/列表
  - [x] test_task_planner.py: 计划创建、子任务状态机
  - **验证**: `uv run pytest tests/ -v` 所有测试通过

# Task Dependencies

- Task 1.2 依赖 Task 1.1
- Task 1.3 依赖 Task 1.2
- Task 1.4 依赖 Task 1.2
- Task 1.5 依赖 Task 1.4
- Task 2.2 依赖 Task 2.1
- Task 3.2 依赖 Task 3.1
- Task 4.2 依赖 Task 4.1
- Task 5.2 依赖 Task 5.1
- Task 5.3 依赖 Task 5.2
- Task 6.2 依赖 Task 6.1
- Phase 3 依赖 Phase 1（子任务执行需要进度反馈）
- Phase 4 依赖 Phase 3（检查点需要子任务信息）
- Phase 5 依赖 Phase 1（ask_user 需要暂停机制）
- Phase 6 依赖 Phase 3（并行执行需要子任务信息）
- Task T.1 依赖所有 Phase 完成

# 并行化机会

- Phase 1 和 Phase 2 可并行（无依赖）
- Task 4.1 和 Task 3.1 可并行（独立模块）
- Phase 5 和 Phase 6 可并行（无依赖）
