# Plan: 重构 CHAT_PAGE 为模块化 HTML/CSS/JS 文件

## Summary

将 `app/service.py` 中 538 行的 `CHAT_PAGE` 内联字符串拆分为三个独立文件：
- `app/static/chat.html` — HTML 结构
- `app/static/chat.css` — 所有样式
- `app/static/chat.js` — 所有脚本

FastAPI 通过 `StaticFiles` 挂载 `/static` 路径，HTML 通过 `<link>` 和 `<script src>` 引用外部资源。

---

## Current State Analysis

- **文件**: `app/service.py`
- **CHAT_PAGE**: 行 36-573，一个 Python `"""..."""` 字符串字面量
  - 行 36-42: `<!DOCTYPE html>` 开头 + `<head>` + CDN marked.js 引用
  - 行 43-157: `<style>...</style>` 内联 CSS（~115 行）
  - 行 158-188: `<body>` HTML 结构（sidebar、main、header、chat、footer）
  - 行 189-571: `<script>...</script>` 内联 JS（~382 行）
  - 行 572-573: `</body></html>` 闭合
- **使用点**: `@app.get("/")` 返回 `CHAT_PAGE`（行 622-623）
- **测试引用**: `test_service.py` 中 `TestChatPageJsSyntax` 类通过 `from app.service import CHAT_PAGE` 解析 JS 做语法验证

---

## Proposed Changes

### 1. 新建 `app/static/chat.css`

**内容**: 提取 `CHAT_PAGE` 中 `<style>...</style>` 之间的所有 CSS（行 44-156）

**变更**: 新建文件，无依赖修改

---

### 2. 新建 `app/static/chat.js`

**内容**: 提取 `CHAT_PAGE` 中 `<script>...</script>` 之间的所有 JS（行 190-570）

**关键**: 这是纯 JS 文件，不再嵌入 Python 字符串，因此：
- 不再需要 Python 字符串转义（`\\'` 直接写成 `\'`，`\\n` 直接写成 `\n`）
- 不再需要 `\\u25b6` 等 Unicode 转义，直接使用字面字符

**变更**: 新建文件，无依赖修改

---

### 3. 新建 `app/static/chat.html`

**内容**: HTML 骨架，引用外部 CSS 和 JS：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentScope Chat</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<link rel="stylesheet" href="/static/chat.css">
</head>
<body>
<!-- sidebar, main, header, chat, footer HTML 结构 -->
<script src="/static/chat.js"></script>
</body>
</html>
```

**变更**: 新建文件，无依赖修改

---

### 4. 修改 `app/service.py`

**变更点**:

1. **删除** `CHAT_PAGE` 字符串字面量（行 36-573）

2. **新增** `load_chat_html()` 函数：
   ```python
   import os
   
   _STATIC_DIR = Path(__file__).parent / "static"
   
   def _load_chat_html() -> str:
       """Load chat.html from static directory."""
       html_path = _STATIC_DIR / "chat.html"
       return html_path.read_text(encoding="utf-8")
   ```

3. **修改** `create_app()` 函数：
   - 新增 `StaticFiles` 挂载：
     ```python
     from fastapi.staticfiles import StaticFiles
     app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
     ```
   - 修改 `index()` 路由：
     ```python
     @app.get("/", response_class=HTMLResponse)
     async def index() -> str:
         return _load_chat_html()
     ```

4. **移除** 不再需要的 `HTMLResponse` import（如果只有 `index` 使用的话；实际上 `index` 仍需要，所以保留）

---

### 5. 修改 `tests/test_service.py`

**变更 `TestChatPageJsSyntax` 类**:

1. `test_js_syntax_valid`: 改为直接读取 `app/static/chat.js` 文件做 `node --check`，不再解析 `CHAT_PAGE` 字符串
2. `test_js_no_unescaped_single_quotes_in_strings`: **删除**，因为 JS 是独立文件，不再有 Python 字符串转义问题

---

## File Changes Summary

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `app/static/chat.css` | 提取 CSS (~115 行) |
| 新建 | `app/static/chat.js` | 提取 JS (~382 行) |
| 新建 | `app/static/chat.html` | HTML 骨架 (~30 行) |
| 修改 | `app/service.py` | 删除 CHAT_PAGE，新增 load_chat_html()，挂载 StaticFiles |
| 修改 | `tests/test_service.py` | 更新 JS 语法测试，删除转义测试 |

---

## Assumptions & Decisions

1. **选方案 B（独立静态文件）** 而非方案 A（读取文件后内联）：
   - 浏览器可缓存 CSS/JS，后续加载更快
   - 开发时修改 CSS/JS 无需重启服务
   - 真正的模块化，维护体验最佳

2. **marked.js 保持 CDN 引用**：不本地化，保持轻量

3. **JS 文件中的 Unicode 字符**：`\u25b6` 等改为直接使用字面字符（`▶`、`✓`、`✗`、`■`、`▼`），因为不再是 Python 字符串

4. **JS 转义修复**：`toggle(\\'expanded\\')` → `toggle(\'expanded\')`，`'\\n'` → `'\n'`，因为不再经过 Python 字符串解析

---

## Verification

1. `node --check app/static/chat.js` — JS 语法正确
2. `uv run pytest tests/test_service.py -v` — 所有测试通过
3. `uv run python -m app.service` — 服务启动正常，访问 `http://localhost:8000/` 页面正常渲染
4. 验证功能：session 列表、聊天、task 提交、ask_user 问题气泡均正常