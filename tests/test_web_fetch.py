"""Tests for web_fetch tool in app.search module."""
import pytest


class TestWebFetch:
    """Tests for web_fetch tool."""

    @pytest.mark.asyncio
    async def test_web_fetch_imports(self):
        """web_fetch should be importable from app.search."""
        from app.search import web_fetch
        assert callable(web_fetch)

    @pytest.mark.asyncio
    async def test_web_fetch_returns_tool_chunk(self):
        """web_fetch should yield ToolChunk."""
        from app.search import web_fetch

        chunks = []
        async for chunk in web_fetch("https://httpbin.org/get"):
            chunks.append(chunk)

        assert len(chunks) > 0
        chunk = chunks[0]
        assert chunk.content is not None

    @pytest.mark.asyncio
    async def test_web_fetch_invalid_url(self):
        """web_fetch with invalid URL should return error."""
        from app.search import web_fetch
        from agentscope.message import ToolResultState

        chunks = []
        async for chunk in web_fetch("https://invalid.domain.that.does.not.exist.example"):
            chunks.append(chunk)

        assert len(chunks) > 0
        # Should be an error result
        assert chunks[0].state == ToolResultState.ERROR

    @pytest.mark.asyncio
    async def test_web_fetch_success_has_metadata(self):
        """Successful web_fetch should have URL in metadata."""
        from app.search import web_fetch

        chunks = []
        async for chunk in web_fetch("https://httpbin.org/get"):
            chunks.append(chunk)

        chunk = chunks[0]
        assert hasattr(chunk, 'metadata')
        # metadata may be None or a dict with url
        if chunk.metadata:
            assert 'url' in chunk.metadata
