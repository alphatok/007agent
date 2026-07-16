---
name: test-generation
description: >-
  为代码生成高质量的单元测试。支持pytest框架，遵循AAA模式（Arrange-Act-Assert）。
  当用户要求生成测试、编写测试用例、提高测试覆盖率时使用。
  不要用于集成测试、端到端测试或性能测试。
---

# Test Generation Skill

## Workflow

### 1. 分析目标代码

- 使用 Read 工具读取目标模块
- 识别所有公共函数、类和方法
- 分析函数签名：参数类型、返回值类型
- 理解函数的核心逻辑和分支条件

### 2. 设计测试用例

对每个函数/方法，覆盖以下场景：

- **正常路径（Happy Path）**：典型输入，预期正常输出
- **边界条件**：空值、零值、极限值、空容器
- **错误处理**：无效输入、异常抛出
- **副作用**：文件操作、网络请求、状态变更（使用 mock）

### 3. 生成测试代码

遵循以下规范：

```python
"""Tests for [module name]."""
import pytest
from unittest.mock import MagicMock, patch

class Test[ClassName]:
    """Tests for [ClassName]."""

    def test_[method]_[scenario](self) -> None:
        """[简要描述测试场景]"""
        # Arrange
        ...

        # Act
        result = ...

        # Assert
        assert result == expected
```

**规范要点：**
- 文件名：`test_[module].py`
- 测试类：`Test[ClassName]`
- 测试方法：`test_[method]_[scenario]`
- 每个测试只验证一个行为
- 使用 `pytest.mark.asyncio` 标记异步测试
- 对 API 调用使用 `unittest.mock.patch` 避免真实请求
- 使用 `pytest.raises` 验证异常

### 4. 输出

使用 Write 工具将测试代码写入 `tests/test_[module].py`。

完成后输出：
```
已生成测试文件: tests/test_[module].py
测试用例数: N
覆盖场景:
  - Happy path: N
  - 边界条件: N
  - 错误处理: N
运行命令: uv run pytest tests/test_[module].py -v
```

## 自由度

低。测试结构、命名规范、断言模式必须严格遵循。