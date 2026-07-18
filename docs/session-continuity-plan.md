# 会话延续与历史管理实现计划

## 1. 概述

当前 Web Chat 每次服务重启丢失上下文，UI 无法查看/切换历史会话。目标：用户不手动新建会话就持续使用同一会话，支持重启恢复、会话列表切换、新建会话。

## 2. 当前状态

- `app/store.py`：SessionStore 已有完整 CRUD（`create/load_session/get/save/delete`）
- `app/service.py`：`chat_stream` 已保存消息到 store，但每次创建新 session，不支持切换
- `app/agent.py`：`build_agent()` 注入 `agent._store` 和 `agent._memory`
- `app/config.py`：已有 `data_dir`、`db_path`，无需新增配置
- Web UI：单栏布局，无 sidebar

## 3. 设计方案

### 3.1 活跃会话追踪

用文件 `data/active_session.txt` 存储当前活跃会话 ID（一行一个字符串）。

**选择理由**：比 SQLite 配置表更简单，零依赖，一行代码读写。

### 3.2 新增 API

| API | 方法 | 说明 |
|-----|------|------|
| `GET /api/sessions/active` | 新增 | 返回 `{session_id, session, messages[]}`（最近 50 条） |
| `POST /api/sessions/{id}/switch` | 新增 | 切换会话：先验证存在 → 再清空 → 最后加载 |
| `POST /api/sessions/new` | 新增 | 新建会话并切换 |
| `GET /api/sessions` | 改造 | 返回列表时，每条附带 `display_name`（取第一条用户消息前 30 字） |

### 3.3 核心流程

**服务启动**（`main()`）：
1. 读 `data/active_session.txt`
2. 有 session_id 且 `store.get_session()` 存在 → `store.load_session(id, agent)` 恢复上下文
3. 无/不存在 → `store.create_session()` → 写入 `active_session.txt`
4. `agent._active_session_id = session_id`

**聊天消息**（`chat_stream`）：
1. 使用 `agent._active_session_id`，不再每次新建
2. `store.save_message(session_id, "user", content)`
3. `agent.reply_stream()` → 收集 `full_reply`
4. `store.save_message(session_id, "assistant", full_reply)`

**切换会话**（`POST /api/sessions/{id}/switch`）—— **先验证再操作**：
1. `store.get_session(target_id)` → 不存在返回 404
2. `agent.state.context.clear()`
3. `store.load_session(target_id, agent, limit=50)`
4. 写入 `active_session.txt`
5. `agent._active_session_id = target_id`
6. 返回新会话信息 + 消息列表

**新建会话**（`POST /api/sessions/new`）：
1. `store.create_session(name=已去时间缀)`
2. `agent.state.context.clear()`
3. 写入 `active_session.txt`
4. `agent._active_session_id = new_id`
5. 返回新会话信息

### 3.4 Session 名称生成

`GET /api/sessions` 返回时，每条 session 附带 `display_name`：
- 查第一条 role="user" 的消息，取 content 前 30 字
- 无消息 → 用 `Session {创建时间}`

### 3.5 Web UI 改动

左右两栏布局：
- **左侧 Sidebar**（240px）：会话列表 + 「+ 新对话」按钮，当前活跃项高亮
- **右侧 Chat**：保持现有聊天体验不变

**JS 行为**：
- 页面加载：调 `GET /api/sessions/active` 渲染活跃会话 + 历史消息
- 点击会话项：调 `POST /api/sessions/{id}/switch`，清空聊天区，渲染历史消息
- 点击新建：调 `POST /api/sessions/new`，清空聊天区
- 发送消息：已有机理不变，后端 `chat_stream` 自动使用 `active_session_id`

### 3.6 不做

会话重命名、删除 UI、搜索、消息编辑、分支对话、增量对比保存。

## 4. 涉及文件

| 文件 | 改动 |
|------|------|
| `app/store.py` | `load_session` 增加 `limit` 参数（默认 50）；新增 `get_first_user_message()` 方法 |
| `app/service.py` | 辅助函数 `_read/write_active_session()`；`main()` 启动恢复；`chat_stream` 改用 `_active_session_id`；新增 3 个 API；改造 `GET /api/sessions` 含 display_name；HTML 改为两栏布局 |
| `tests/test_service.py` | 5 个会话管理测试用例 |

## 5. 实现步骤

### Step 1：store.py 改造
- `load_session(self, session_id, agent, limit=50)`：支持限制加载条数
- `get_first_user_message(self, session_id) -> str | None`：获取第一条用户消息内容

### Step 2：service.py 后端
- 新增辅助函数 `_read_active_session(data_dir)` / `_write_active_session(data_dir, session_id)`
- `main()` 启动时：恢复活跃会话或创建新会话
- `chat_stream`：改用 `agent._active_session_id`，不再每次新建
- 新增 `GET /api/sessions/active`：返回当前活跃会话 + 最近 50 条消息
- 新增 `POST /api/sessions/{id}/switch`：先验证再切换（原子性保障）
- 新增 `POST /api/sessions/new`：新建并切换
- 改造 `GET /api/sessions`：返回 `display_name` 字段

### Step 3：Web UI 两栏布局
- HTML/CSS 改为 flex 两栏布局（左侧 240px sidebar + 右侧聊天区）
- 左侧 sidebar：会话列表 + 新建按钮 + 活跃高亮
- 页面加载：调 `/api/sessions/active` 渲染
- 会话切换/新建 JS 逻辑

### Step 4：测试
- 5 个测试用例（见下）

## 6. 测试用例

| # | 场景 | 测试点 | 预期 |
|---|------|--------|------|
| 1 | 首次启动无历史 | 无 `active_session.txt` 无任何 session | 自动创建新会话，返回空消息列表 |
| 2 | 聊天后重启 | 1 条对话后停服再启 | 恢复上次会话，历史消息可见 |
| 3 | 新建会话 | 点击新建 | 新会话创建，`active_session` 更新，消息列表为空 |
| 4 | 切换会话 | 2 个会话间切换 | 消息正确加载，`active_session` 更新 |
| 5 | 切换不存在的会话 | 传入无效 session_id | 返回 404，当前会话不变，context 未清空 |

## 7. 验证

```bash
# 运行测试
uv run pytest tests/test_service.py -v -x -s

# 手动验证 API
curl http://localhost:8000/api/sessions/active
curl http://localhost:8000/api/sessions
curl -X POST http://localhost:8000/api/sessions/new
curl -X POST http://localhost:8000/api/sessions/{id}/switch
```
__tr_native_ec=$?; pwd -P >| '/var/folders/k9/0952msvs7n5djrc0lc_x78qw0000gn/T/trae-agent-toolhost-501/jobs/job-30049b96f71f46f98e86d46510911668/cwd.txt'; exit "$__tr_native_ec"