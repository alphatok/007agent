# Checklist: 长程任务能力增强

## Phase 1: 进度反馈

- [x] TaskRecord 新增 progress/current_step/steps 字段，默认值正确
- [x] update_progress() 方法更新字段并持久化到 JSON 文件
- [x] report_progress 工具已注册到 build_toolkit()，Agent 可调用
- [x] GET /api/tasks/{task_id}/stream 端点返回 SSE 格式数据
- [x] SSE 连接在任务完成后正确关闭
- [x] Web UI 提交任务后显示进度条，实时更新
- [x] 进度条在任务完成后自动移除

## Phase 2: 重试机制

- [x] retry_on_failure 装饰器正确实现指数退避
- [x] 可重试异常（ConnectionError, TimeoutError）触发重试
- [x] 不可重试异常（PermissionError）立即失败
- [x] 重试次数达到上限后返回最终错误
- [x] 重试参数可通过 config 配置
- [x] web_search 和 web_fetch 工具启用重试

## Phase 3: 任务规划

- [x] plan_task 工具返回子任务列表，状态均为 pending
- [x] mark_step_complete() 正确更新子任务状态
- [x] get_next_pending_step() 返回下一个待执行子任务
- [x] 子任务失败后根据策略处理（重试/跳过/中止）
- [x] 系统提示词包含长任务执行规范
- [x] Agent 收到多步骤任务时先调用 plan_task

## Phase 4: 断点续传

- [x] save_checkpoint() 保存数据到 JSON 文件
- [x] load_checkpoint() 正确恢复数据
- [x] 检查点文件路径为 data/checkpoints/{task_id}.json
- [x] execute() 每完成一个子任务保存检查点
- [x] 服务启动时检测未完成任务并加载检查点  <!-- 已实现：main() 中检测 pending 任务并恢复 -->
- [x] resume_task() 从中断处继续执行

## Phase 5: 人机协作

- [x] ask_user 工具将任务状态设为 waiting_user  <!-- 通过独立 asyncio.Event 机制实现，功能正确等价 -->
- [x] asyncio.Event 正确等待用户响应
- [x] 超时 5 分钟后任务标记为 timeout
- [x] POST /api/tasks/{task_id}/respond 接收响应并触发恢复
- [x] Web UI 检测 waiting_user 状态显示弹窗
- [x] 用户选择后 Agent 继续执行

## Phase 6: 并行执行

- [x] 无依赖子任务通过 asyncio.gather 并行执行
- [x] 有依赖子任务按拓扑排序执行
- [x] 并行任务总体进度 = 已完成 / 总数
- [x] 每个子任务独立报告进度，互不干扰
- [x] 并行任务完成后结果正确汇总

## 回归测试

- [x] 所有现有测试通过（108 个）
- [x] 新增测试全部通过
- [x] 服务启动正常，无 import 错误
- [x] Web UI 基本功能正常（聊天、会话切换）
