"""Tests for app.cli module."""
import pytest


class TestStreamReply:
    """Tests for _stream_reply function."""

    @pytest.mark.asyncio
    async def test_full_response_initialized_before_loop(self):
        """Verify full_response is initialized before the async for loop.

        Regression test: full_response was only assigned inside
        TEXT_BLOCK_DELTA branch, causing UnboundLocalError when the
        agent reply produced no text deltas (e.g., only tool calls).
        """
        from app.cli import _stream_reply
        import inspect

        source = inspect.getsource(_stream_reply)
        # full_response must be initialized before the async for loop
        init_idx = source.index("full_response")
        loop_idx = source.index("async for evt in")
        assert init_idx < loop_idx, (
            "full_response must be initialized BEFORE the async for loop"
        )

    @pytest.mark.asyncio
    async def test_stream_reply_with_no_text_deltas(self):
        """_stream_reply should not crash when agent produces no text deltas."""
        from unittest.mock import MagicMock
        from agentscope.event import EventType
        from agentscope.message import ToolResultState
        from app.cli import _stream_reply

        mock_agent = MagicMock()
        mock_agent.state = MagicMock()
        mock_agent.state.summary = None

        # Simulate events with only tool calls, no text deltas
        class MockEvent:
            def __init__(self, type_, delta=None, tool_call_id=None,
                         tool_call_name=None, state=None):
                self.type = type_
                self.delta = delta
                self.tool_call_id = tool_call_id
                self.tool_call_name = tool_call_name
                self.state = state

        events = [
            MockEvent(EventType.REPLY_START),
            MockEvent(EventType.TOOL_CALL_START, tool_call_id="1",
                      tool_call_name="test_tool"),
            MockEvent(EventType.TOOL_RESULT_END, tool_call_id="1",
                      state=ToolResultState.SUCCESS),
            MockEvent(EventType.REPLY_END),
        ]

        async def mock_stream(*args, **kwargs):
            for evt in events:
                yield evt

        mock_agent.reply_stream = mock_stream
        # Should not raise UnboundLocalError
        await _stream_reply(mock_agent, "hello")


class TestCli:
    """Tests for CLI entry point."""

    def test_cli_module_exists(self) -> None:
        """CLI module should be importable."""
        from app import cli
        assert cli is not None

    def test_run_cli_is_async_function(self) -> None:
        """run_cli should be an async function."""
        import inspect
        from app.cli import run_cli

        assert inspect.iscoroutinefunction(run_cli)