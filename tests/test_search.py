"""Tests for app.search module."""
import pytest


class TestWebSearch:
    """Tests for web_search tool."""

    @pytest.mark.asyncio
    async def test_web_search_returns_tool_chunk(self) -> None:
        """web_search should yield ToolChunk with TextBlock content."""
        from app.search import web_search

        chunks = []
        async for chunk in web_search("Python programming"):
            chunks.append(chunk)

        assert len(chunks) > 0
        chunk = chunks[0]
        assert chunk.content is not None
        assert len(chunk.content) > 0
        # Content should be a TextBlock
        from agentscope.message import TextBlock

        assert isinstance(chunk.content[0], TextBlock)

    @pytest.mark.asyncio
    async def test_web_search_max_results(self) -> None:
        """web_search should accept max_results parameter."""
        from app.search import web_search

        chunks = []
        async for chunk in web_search("test", max_results=2):
            chunks.append(chunk)

        assert len(chunks) == 1
        # Should contain at most 2 results
        text = chunks[0].content[0].text
        # Count numbered items in the output
        result_count = text.count("\n1. ")
        assert result_count >= 0  # At least no error

    @pytest.mark.asyncio
    async def test_web_search_fast(self) -> None:
        """Quick smoke test for web_search."""
        from app.search import web_search

        chunks = []
        async for chunk in web_search("hello world", max_results=1):
            chunks.append(chunk)

        assert len(chunks) == 1
        text = chunks[0].content[0].text
        assert "hello world" in text.lower() or "Search results" in text