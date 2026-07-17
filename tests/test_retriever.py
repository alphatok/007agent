"""Tests for app.retriever module — HybridRetriever."""
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_dirs():
    """Create temporary directories for SQLite and zvec."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        zvec_path = os.path.join(tmpdir, "zvec")
        yield db_path, zvec_path


class TestHybridRetriever:
    """Tests for HybridRetriever with zvec-based search."""

    def test_search_returns_results(self, temp_dirs: tuple) -> None:
        """search should return results from SQLite when zvec is not available."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.retriever import HybridRetriever

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="Redis 缓存策略：使用 LRU")
        store.add_memory(type="semantic", content="Python 依赖管理：使用 uv")

        retriever = HybridRetriever(db_path, zvec_path, store)
        results = retriever.search("Redis", top_k=5)
        assert len(results) > 0

    def test_search_empty_query(self, temp_dirs: tuple) -> None:
        """search with empty query should return empty list."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.retriever import HybridRetriever

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="test")

        retriever = HybridRetriever(db_path, zvec_path, store)
        results = retriever.search("", top_k=5)
        assert results == []

    def test_search_by_type(self, temp_dirs: tuple) -> None:
        """search should filter by memory_type."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.retriever import HybridRetriever

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="语义记忆")
        store.add_memory(type="episodic", content="情景记忆")

        retriever = HybridRetriever(db_path, zvec_path, store)
        results = retriever.search("记忆", memory_types=["semantic"], top_k=5)
        assert len(results) == 1
        assert results[0]["type"] == "semantic"

    def test_search_no_results(self, temp_dirs: tuple) -> None:
        """search with no matching memories should return empty list."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.retriever import HybridRetriever

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="Python 依赖管理")

        retriever = HybridRetriever(db_path, zvec_path, store)
        results = retriever.search("zzzzz_nonexistent_query", top_k=5)
        assert results == []

    def test_search_keyword(self, temp_dirs: tuple) -> None:
        """Keyword search should match content exactly."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.retriever import HybridRetriever

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="Redis 缓存策略")
        store.add_memory(type="semantic", content="Python uv 包管理")

        retriever = HybridRetriever(db_path, zvec_path, store)
        results = retriever.search("Redis", top_k=5)
        assert len(results) == 1
        assert "Redis" in results[0]["content"]

    def test_search_ranked(self, temp_dirs: tuple) -> None:
        """Results should be ordered by relevance."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore
        from app.retriever import HybridRetriever

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="Redis 连接池配置", importance=0.9)
        store.add_memory(type="semantic", content="Redis 基础概念", importance=0.5)

        retriever = HybridRetriever(db_path, zvec_path, store)
        results = retriever.search("Redis 连接", top_k=5)
        assert len(results) >= 1
        # Higher importance should rank higher
        if len(results) >= 2:
            assert results[0]["importance"] >= results[1]["importance"]