# 长程任务能力增强 Spec

## Why
当前 Agent 任务系统只支持基本异步执行，长程任务缺少进度反馈、容错重试、任务规划、断点续传、人机协作和并行执行能力，导致用户体验差、任务可靠性低。

## What Changes
- **Phase 1**: 进度反馈 – TaskRecord 增加 progress/current_step/steps 字段，新增 report_progress 工具，SSE 进度流，Web UI 进度条
- **Phase 2**: 重试机制 – 新增 retry_on_failure 装饰器，指数退避，可重试/不可重试分类
- **Phase 3**: 任务规划 – plan_task 工具，子任务状态机，系统提示词增强
- **Phase 4**: 断点续传 – checkpoint 保存/恢复，服务重启后继续执行
- **Phase 5**: 人机协作 – ask_user 工具，Agent 暂停等待用户输入
- **Phase 6**: 并行执行 – 子任务并行调度，结果汇总

## Impact
- Affected specs: 任务管理、工具系统、Web UI
- Affected code: `app/task_manager.py`, `app/tools.py`, `app/service.py`, `app/config.py`, `app/agent.py`
- New files: `app/retry.py`, `app/task_planner.py`, `app/checkpoint.py`

---

## ADDED Requirements

### Requirement: 进度反馈
系统 SHALL 支持任务执行过程中实时报告进度，并通过 SSE 推送给客户端。

#### Scenario: Agent 调用 report_progress 更新进度
- **WHEN** Agent 在任务执行中调用 report_progress(progress=50, current_step="正在搜索互联网")
- **THEN** TaskRecord.progress 更新为 50，TaskRecord.current_step 更新为 "正在搜索互联网"
- **AND** 连接的 SSE 客户端收到 `{"type":"progress","progress":50,"current_step":"正在搜索互联网"}`

#### Scenario: 客户端通过 SSE 接收进度
- **WHEN** 客户端连接 GET /api/tasks/{task_id}/stream
- **THEN** 持续接收 progress 事件直到任务完成
- **AND** 任务完成时收到 `{"type":"done","result":"..."}`

#### Scenario: Web UI 显示进度条
- **WHEN** 用户在 Web UI 提交任务
- **THEN** 页面显示进度条和当前步骤文字
- **AND** 进度条实时更新

### Requirement: 重试机制
系统 SHALL 在工具调用失败时自动重试，使用指数退避策略。

#### Scenario: 临时错误自动重试
- **WHEN** 工具调用遇到 ConnectionError 或 TimeoutError
- **THEN** 系统自动重试最多 3 次，每次延迟递增（1s, 2s, 4s）
- **AND** 3 次后仍失败则返回错误

#### Scenario: 不可重试错误直接失败
- **WHEN** 工具调用遇到 PermissionError 或参数错误
- **THEN** 系统不重试，立即返回失败

#### Scenario: 重试次数可配置
- **WHEN** 配置 tool_retry_max=5
- **THEN** 工具最多重试 5 次

### Requirement: 任务规划
系统 SHALL 支持 Agent 将复杂任务分解为子任务并跟踪执行。

#### Scenario: Agent 创建任务计划
- **WHEN** Agent 调用 plan_task(goal="重构项目", subtasks=["分析代码结构","生成测试","重构模块"])
- **THEN** 创建 3 个子任务，状态均为 pending
- **AND** 返回子任务 ID 列表

#### Scenario: 子任务按序执行
- **WHEN** 子任务 1 完成
- **THEN** 自动开始子任务 2
- **AND** 子任务进度通过 report_progress 更新

#### Scenario: 子任务失败处理
- **WHEN** 子任务执行失败
- **THEN** 根据策略决定：重试 / 跳过 / 中止整体任务

### Requirement: 断点续传
系统 SHALL 支持保存任务执行中间状态，在服务重启后从断点恢复。

#### Scenario: 保存检查点
- **WHEN** Agent 调用 save_checkpoint(data={"step":3,"result":"partial"})
- **THEN** 检查点数据持久化到磁盘
- **AND** 可通过任务 ID 恢复

#### Scenario: 服务重启后恢复
- **WHEN** 服务重启，存在未完成的任务
- **THEN** 自动加载最近检查点
- **AND** Agent 从中断处继续执行

### Requirement: 人机协作
系统 SHALL 支持 Agent 在长任务中暂停并询问用户。

#### Scenario: Agent 暂停询问用户
- **WHEN** Agent 调用 ask_user(question="使用哪个数据库？", options=["SQLite","PostgreSQL"])
- **THEN** 任务状态变为 waiting_user
- **AND** Web UI 弹出选择框
- **AND** 用户选择后 Agent 继续执行

#### Scenario: 用户超时未响应
- **WHEN** Agent 等待用户输入超过 5 分钟
- **THEN** 任务标记为 timeout，可选择恢复或取消

### Requirement: 并行执行
系统 SHALL 支持多个独立子任务并行执行。

#### Scenario: 独立子任务并行
- **WHEN** 任务计划包含 3 个无依赖的子任务
- **THEN** 3 个子任务同时执行
- **AND** 全部完成后汇总结果

#### Scenario: 并行任务进度汇总
- **WHEN** 并行子任务执行中
- **THEN** 总体进度 = 已完成子任务数 / 总子任务数
- **AND** 每个子任务可独立报告进度
