"""Tests for app.memory_tool module — memory-related FunctionTools."""
import os
import tempfile

import pytest


@pytest.fixture
def temp_dirs():
    """Create temporary directories for SQLite and zvec."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        zvec_path = os.path.join(tmpdir, "zvec")
        yield db_path, zvec_path


class TestMemoryTools:
    """Tests for memory tool functions."""

    def test_add_memory_tool(self, temp_dirs: tuple) -> None:
        """add_memory tool should return SUCCESS."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.memory_tool import (
            _add_memory, _list_memories, _search_memory, _forget_memory,
            _store, set_memory_store,
        )

        store = MemoryStore(db_path, zvec_path)
        set_memory_store(store)

        import asyncio
        async def run():
            results = []
            async for chunk in _add_memory(content="测试记忆", type="semantic"):
                results.append(chunk)
            assert len(results) > 0
            from agentscope.message import ToolResultState
            assert results[-1].state == ToolResultState.SUCCESS

        asyncio.run(run())

    def test_list_memories_tool(self, temp_dirs: tuple) -> None:
        """list_memories tool should return SUCCESS."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.memory_tool import (
            _add_memory, _list_memories, _search_memory, _forget_memory,
            _store, set_memory_store,
        )

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="测试记忆")
        set_memory_store(store)

        import asyncio
        async def run():
            results = []
            async for chunk in _list_memories():
                results.append(chunk)
            assert len(results) > 0
            from agentscope.message import ToolResultState
            assert results[-1].state == ToolResultState.SUCCESS

        asyncio.run(run())

    def test_search_memory_tool(self, temp_dirs: tuple) -> None:
        """search_memory tool should return SUCCESS."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.retriever import HybridRetriever
        from app.memory_tool import (
            _add_memory, _list_memories, _search_memory, _forget_memory,
            _store, set_memory_store, set_retriever,
        )

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="Redis 缓存策略")
        set_memory_store(store)
        set_retriever(HybridRetriever(db_path, zvec_path, store))

        import asyncio
        async def run():
            results = []
            async for chunk in _search_memory(query="Redis"):
                results.append(chunk)
            assert len(results) > 0
            from agentscope.message import ToolResultState
            assert results[-1].state == ToolResultState.SUCCESS

        asyncio.run(run())

    def test_forget_memory_tool(self, temp_dirs: tuple) -> None:
        """forget_memory tool should return SUCCESS for valid ID."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.memory_tool import (
            _add_memory, _list_memories, _search_memory, _forget_memory,
            _store, set_memory_store,
        )

        store = MemoryStore(db_path, zvec_path)
        memory_id = store.add_memory(type="semantic", content="待删除")
        set_memory_store(store)

        import asyncio
        async def run():
            results = []
            async for chunk in _forget_memory(memory_id=memory_id):
                results.append(chunk)
            assert len(results) > 0
            from agentscope.message import ToolResultState
            assert results[-1].state == ToolResultState.SUCCESS
            assert store.get_memory(memory_id) is None

        asyncio.run(run())

    def test_forget_memory_nonexistent(self, temp_dirs: tuple) -> None:
        """forget_memory should return ERROR for nonexistent ID."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.memory_tool import (
            _add_memory, _list_memories, _search_memory, _forget_memory,
            _store, set_memory_store,
        )

        store = MemoryStore(db_path, zvec_path)
        set_memory_store(store)

        import asyncio
        async def run():
            results = []
            async for chunk in _forget_memory(memory_id="nonexistent"):
                results.append(chunk)
            from agentscope.message import ToolResultState
            assert results[-1].state == ToolResultState.ERROR

        asyncio.run(run())

    def test_get_tools(self, temp_dirs: tuple) -> None:
        """get_memory_tools should return 5 FunctionTools."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.memory_tool import get_memory_tools, set_memory_store

        store = MemoryStore(db_path, zvec_path)
        set_memory_store(store)

        tools = get_memory_tools()
        assert len(tools) == 5

        from agentscope.tool import FunctionTool
        for tool in tools:
            assert isinstance(tool, FunctionTool)