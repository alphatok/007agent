"""Tests for app.memory module — MemoryStore."""
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


class TestMemoryStore:
    """Tests for MemoryStore CRUD and lifecycle."""

    def test_add_memory(self, temp_dirs: tuple) -> None:
        """add_memory should return a UUID string."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        memory_id = store.add_memory(
            type="semantic",
            content="用户偏好使用 uv 管理 Python 依赖",
        )
        assert isinstance(memory_id, str)
        assert len(memory_id) == 36

    def test_get_memory(self, temp_dirs: tuple) -> None:
        """get_memory should return memory dict."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        memory_id = store.add_memory(
            type="semantic",
            content="测试记忆",
            importance=0.8,
        )
        mem = store.get_memory(memory_id)
        assert mem is not None
        assert mem["content"] == "测试记忆"
        assert mem["type"] == "semantic"
        assert mem["importance"] == 0.8

    def test_get_memory_nonexistent(self, temp_dirs: tuple) -> None:
        """get_memory should return None for nonexistent ID."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        result = store.get_memory("nonexistent")
        assert result is None

    def test_update_memory(self, temp_dirs: tuple) -> None:
        """update_memory should update fields."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        memory_id = store.add_memory(
            type="semantic",
            content="原始内容",
        )
        result = store.update_memory(
            memory_id, content="更新后内容", importance=0.9
        )
        assert result is True

        mem = store.get_memory(memory_id)
        assert mem is not None
        assert mem["content"] == "更新后内容"
        assert mem["importance"] == 0.9

    def test_delete_memory(self, temp_dirs: tuple) -> None:
        """delete_memory should remove from SQLite."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        memory_id = store.add_memory(
            type="semantic",
            content="待删除",
        )
        assert store.delete_memory(memory_id) is True
        assert store.get_memory(memory_id) is None

    def test_list_memories(self, temp_dirs: tuple) -> None:
        """list_memories should return all memories."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="Memory 1")
        store.add_memory(type="episodic", content="Memory 2")

        memories = store.list_memories()
        assert len(memories) == 2

    def test_list_memories_by_type(self, temp_dirs: tuple) -> None:
        """list_memories should filter by type."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(type="semantic", content="S1")
        store.add_memory(type="episodic", content="E1")

        semantic = store.list_memories(type="semantic")
        assert len(semantic) == 1
        assert semantic[0]["type"] == "semantic"

        episodic = store.list_memories(type="episodic")
        assert len(episodic) == 1
        assert episodic[0]["type"] == "episodic"

    def test_memory_types(self, temp_dirs: tuple) -> None:
        """All three memory types should be supported."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        eid = store.add_memory(type="episodic", content="上周讨论了 Redis 缓存策略")
        sid = store.add_memory(type="semantic", content="用户偏好 uv 管理依赖")
        pid = store.add_memory(type="procedural", content="修复 N+1 查询标准步骤")

        assert store.get_memory(eid)["type"] == "episodic"
        assert store.get_memory(sid)["type"] == "semantic"
        assert store.get_memory(pid)["type"] == "procedural"

    def test_consolidate(self, temp_dirs: tuple) -> None:
        """consolidate: high-access episodic -> semantic."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        memory_id = store.add_memory(
            type="episodic",
            content="讨论了 Redis 缓存策略",
            importance=0.7,
        )
        # Simulate high access
        for _ in range(5):
            store.get_memory(memory_id)

        count = store.consolidate(threshold=3)
        assert count == 1
        mem = store.get_memory(memory_id)
        assert mem["type"] == "semantic"

    def test_decay(self, temp_dirs: tuple) -> None:
        """decay: low importance + old -> delete."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        store.add_memory(
            type="episodic",
            content="不重要",
            importance=0.1,
        )
        store.add_memory(
            type="semantic",
            content="重要",
            importance=0.9,
        )

        count = store.decay(
            max_age_days=0,  # immediately
            importance_threshold=0.3,
        )
        assert count == 1
        memories = store.list_memories()
        assert len(memories) == 1
        assert memories[0]["content"] == "重要"

    def test_extract_from_session(self, temp_dirs: tuple) -> None:
        """extract_from_session should call LLM and create memories."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store = MemoryStore(db_path, zvec_path)
        messages = [
            {"role": "user", "content": "我想用 uv 管理 Python 依赖"},
            {"role": "assistant", "content": "好的，uv 是一个快速的 Python 包管理器..."},
        ]

        # Mock the LLM extraction
        with patch.object(store, "_extract_with_llm") as mock_extract:
            mock_extract.return_value = [
                ("semantic", "用户偏好使用 uv 管理 Python 依赖"),
            ]
            ids = store.extract_from_session("session-1", messages)
            assert len(ids) == 1
            mem = store.get_memory(ids[0])
            assert mem["type"] == "semantic"
            assert "uv" in mem["content"]

    def test_persistence_across_instances(self, temp_dirs: tuple) -> None:
        """Memories should persist across MemoryStore instances."""
        db_path, zvec_path = temp_dirs
        from app.memory import MemoryStore

        store1 = MemoryStore(db_path, zvec_path)
        memory_id = store1.add_memory(
            type="semantic",
            content="持久化测试",
        )

        store2 = MemoryStore(db_path, zvec_path)
        mem = store2.get_memory(memory_id)
        assert mem is not None
        assert mem["content"] == "持久化测试"