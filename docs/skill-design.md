# Skill System Design & Specification

## 1. AgentScope Skill 机制调研结论

AgentScope 2.0 内置了一套完整的 Skill 系统，与 Tool 系统是**正交的**：

| 维度 | Tool | Skill |
|------|------|-------|
| 本质 | 可执行函数 | 指令文档（SKILL.md） |
| 调用方式 | Agent 直接调用工具 | Agent 通过 `Skill` 工具**读取**指令，再按指令执行 |
| 注册方式 | `Toolkit(tools=[...])` | `Toolkit(skills_or_loaders=[...])` |
| 加载方式 | 直接注册 Python 对象 | 通过 `SkillLoader` 扫描目录加载 SKILL.md |
| 协议 | Python FunctionTool | SKILL.md + YAML frontmatter |

### 核心类

- `Skill` dataclass: `name`, `description`, `dir`, `markdown`, `updated_at`
- `SkillLoaderBase`: 抽象基类，定义 `async list_skills() -> list[Skill]`
- `LocalSkillLoader`: 扫描本地目录，读取 SKILL.md，解析 YAML frontmatter，按文件修改时间缓存
- `SkillViewer`: 内置工具，名称 `"Skill"`，Agent 用它读取 Skill 完整指令

### 工作流程

```
1. 启动时 → LocalSkillLoader 扫描目录 → 解析 SKILL.md frontmatter
2. 对话时 → 系统提示词注入 Skill 列表（name + description）
3. Agent 判断需要时 → 调用 Skill("skill-name") 工具
4. SkillViewer 返回 → SKILL.md 的 markdown 内容
5. Agent 按指令 → 使用现有工具完成任务
```

---

## 2. 设计方案：双层 Skill 体系

结合 AgentScope 原生机制和项目现有实践，采用**双层 Skill 体系**：

```
skills/
├── __init__.py              # Tool Skill 自动发现（现有）
│
├── anthropic_skill.py       # [Tool Skill] Anthropic Claude API 工具
├── openai_skill.py          # [Tool Skill] OpenAI GPT API 工具
│
├── code-review/             # [Instruction Skill] 代码审查
│   └── SKILL.md
└── test-generation/         # [Instruction Skill] 测试生成
    └── SKILL.md
```

### Layer 1: Tool Skill（工具型技能）

- **定义**: Python 模块，导出 `get_tools() -> list[FunctionTool]`
- **用途**: 为 Agent 提供**新的工具能力**（如调用 Anthropic/OpenAI API）
- **加载**: 启动时自动扫描 `skills/*.py`，注册到 `Toolkit.tools`
- **规范**: 遵循 FunctionTool + ToolChunk + TextBlock + ToolResultState 模式

### Layer 2: Instruction Skill（指令型技能）

- **定义**: 目录 + SKILL.md 文件，包含 YAML frontmatter + Markdown 指令
- **用途**: 教 Agent **如何使用已有工具**完成特定领域任务
- **加载**: 通过 `LocalSkillLoader` 扫描 `skills/` 目录下的子目录
- **规范**: 遵循 SKILL.md 规范（见下文）

---

## 3. SKILL.md 规范

### 3.1 目录结构

```
skill-name/              # 目录名 = frontmatter name
├── SKILL.md             # 必需：元数据 + 核心指令（<500行）
├── scripts/             # 可选：确定性脚本
├── references/          # 可选：补充文档
└── assets/              # 可选：模板、静态文件
```

### 3.2 Frontmatter 规范

```yaml
---
name: code-review                          # 1-64字符，小写+数字+连字符，必须与目录名一致
description: >-                            # 最多1024字符，第三人称
  对代码变更进行系统性审查。检查代码质量、安全性、性能、可维护性。
  当用户要求审查代码、检查PR、评估代码质量时使用。
  不要用于简单的代码解释或文档生成。
---
```

**命名规则**:
- 格式: `动词-ing-名词`，如 `code-review`, `test-generation`
- 仅小写字母 + 数字 + 连字符，不能有连续连字符
- 必须与父目录名完全一致

**描述规则**:
- 第三人称（"对代码变更..." 而非 "我可以..."）
- 包含触发关键词 + 使用场景
- 包含反向触发词（什么情况下不该用）
- 1024 字符以内

### 3.3 内容编写规范

1. **简洁至上**: 主体 ≤500 行，不解释 AI 已知概念
2. **分步骤编号**: 工作流用严格时序步骤
3. **第三人称祈使**: "提取文本..." 而非 "我将提取..."
4. **术语一致**: 一个概念一个词贯穿全文
5. **渐进式披露**: 主文件做导航，细节放到 references/
6. **提供模板**: 结构化输出放 assets/，指示 Agent 复制结构
7. **一级引用深度**: 引用文件只放一层，不嵌套
8. **避免时效性信息**: 不写"当前最新版本是 v3.2"
9. **正斜杠路径**: `references/schema.md` 而非 `references\schema.md`

### 3.4 自由度分级

| 自由度 | 适用场景 | 写法 |
|--------|----------|------|
| 高 | 创意任务 | 提供质量标准，不限制方法 |
| 中 | 有首选模式 | 提供建议模式，允许变体 |
| 低 | 必须严格流程 | 详细步骤清单，不允许偏离 |

---

## 4. 实现计划

### 4.1 目录结构调整

```
skills/
├── __init__.py              # 不变，仍为 Tool Skill 发现
├── anthropic_skill.py       # 不变
├── openai_skill.py          # 不变
│
├── code-review/             # 新增
│   └── SKILL.md
└── test-generation/         # 新增
    └── SKILL.md
```

### 4.2 app/tools.py 改造

```python
async def build_toolkit(config: Config) -> Toolkit:
    # Tool Skills (现有)
    skill_tools = discover_skills()
    all_tools = list(BUILTIN_TOOLS) + skill_tools

    # MCP
    mcps = [...]
    
    # Instruction Skills (新增) - 通过 skills_or_loaders 注册
    return Toolkit(
        tools=all_tools,
        skills_or_loaders=["skills/"],  # LocalSkillLoader 扫描 SKILL.md
        mcps=mcps if mcps else None,
    )
```

### 4.3 app/agent.py 改造

```python
def build_agent(config: Config, toolkit: Toolkit) -> Agent:
    # 获取 skill 指令并注入到 system prompt
    skill_instructions = await toolkit.get_skill_instructions()
    # ... 注入到 agent 系统提示
```

### 4.4 创建两个 Instruction Skill

| Skill | 描述 | 用途 |
|-------|------|------|
| `code-review` | 代码审查 | 教 Agent 如何审查代码变更 |
| `test-generation` | 测试生成 | 教 Agent 如何生成高质量测试 |

### 4.5 测试

- 测试 `LocalSkillLoader` 正确加载 SKILL.md
- 测试 `Toolkit.get_skill_instructions()` 返回正确提示词
- 测试 `SkillViewer` 工具可被调用并返回内容
- 保持现有 29 个测试全部通过