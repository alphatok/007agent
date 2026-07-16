"""Tests for app.subagent module."""
import pytest


class TestSubagentLoader:
    """Tests for SubagentLoader."""

    def test_loads_code_reviewer_config(self) -> None:
        """Should load code-reviewer AGENT.md config."""
        from app.subagent import SubagentConfig, SubagentLoader

        loader = SubagentLoader()
        config = loader.load("code-reviewer")
        assert config is not None
        assert isinstance(config, SubagentConfig)
        assert config.name == "code-reviewer"
        assert "审查代码变更" in config.description
        assert "Read" in config.tools
        assert "Grep" in config.tools
        assert config.model == "deepseek-v4-pro"
        assert len(config.system_prompt) > 0

    def test_loads_test_generator_config(self) -> None:
        """Should load test-generator AGENT.md config."""
        from app.subagent import SubagentConfig, SubagentLoader

        loader = SubagentLoader()
        config = loader.load("test-generator")
        assert config is not None
        assert isinstance(config, SubagentConfig)
        assert config.name == "test-generator"
        assert "生成测试" in config.description
        assert "Write" in config.tools
        assert len(config.system_prompt) > 0

    def test_returns_none_for_missing(self) -> None:
        """Should return None for nonexistent subagent."""
        from app.subagent import SubagentLoader

        loader = SubagentLoader()
        assert loader.load("nonexistent") is None

    def test_lists_all_configs(self) -> None:
        """Should list all available subagents."""
        from app.subagent import SubagentLoader

        loader = SubagentLoader()
        configs = loader.list_all()
        assert isinstance(configs, dict)
        assert "code-reviewer" in configs
        assert "test-generator" in configs
        assert len(configs) >= 2


class TestSubagentConfig:
    """Tests for SubagentConfig fields."""

    def test_config_has_required_fields(self) -> None:
        """SubagentConfig should have all required fields."""
        from app.subagent import SubagentConfig

        config = SubagentConfig(
            name="test",
            description="A test subagent",
            tools=["Read", "Grep"],
            model="deepseek-v4-pro",
            system_prompt="You are a test subagent.",
        )
        assert config.name == "test"
        assert config.description == "A test subagent"
        assert config.tools == ["Read", "Grep"]
        assert config.model == "deepseek-v4-pro"
        assert config.system_prompt == "You are a test subagent."


class TestSubagentRunner:
    """Tests for SubagentRunner."""

    def test_runner_initialization(self) -> None:
        """Should initialize with config and loader."""
        from app.config import Config
        from app.subagent import SubagentLoader, SubagentRunner

        config = Config(deepseek_api_key="sk-test")
        loader = SubagentLoader()
        runner = SubagentRunner(config, loader)
        assert runner is not None

    @pytest.mark.asyncio
    async def test_runner_raises_for_missing_subagent(self) -> None:
        """Should raise ValueError for nonexistent subagent."""
        from app.config import Config
        from app.subagent import SubagentLoader, SubagentRunner

        config = Config(deepseek_api_key="sk-test")
        loader = SubagentLoader()
        runner = SubagentRunner(config, loader)

        with pytest.raises(ValueError, match="not found"):
            await runner.run("nonexistent", "test task")


class TestDelegateSubagent:
    """Tests for delegate_subagent FunctionTool."""

    @pytest.mark.asyncio
    async def test_yields_error_when_runner_not_set(self) -> None:
        """Should yield ERROR when SubagentRunner is not initialized."""
        from app.subagent import delegate_subagent, set_subagent_runner

        # Reset the global runner
        set_subagent_runner(None)  # type: ignore[arg-type]

        chunks = []
        async for chunk in delegate_subagent(
            subagent_name="code-reviewer",
            task="test",
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        from agentscope.message import ToolResultState

        assert chunks[0].state == ToolResultState.ERROR
        assert "not initialized" in chunks[0].content[0].text

    def test_get_tools_returns_function_tool(self) -> None:
        """get_tools should return a list with one FunctionTool."""
        from app.subagent import get_tools
        from agentscope.tool import FunctionTool

        tools = get_tools()
        assert len(tools) == 1
        assert isinstance(tools[0], FunctionTool)