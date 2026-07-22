"""Tests for app.checkpoint module - save/load/list/delete."""
import json
import os
import tempfile
import pytest


class TestCheckpoint:
    """Tests for checkpoint save/load/list/delete."""

    @pytest.fixture
    def data_dir(self):
        """Create a temp directory for checkpoints."""
        with tempfile.TemporaryDirectory() as d:
            yield d

    def test_imports(self):
        """All checkpoint functions should be importable."""
        from app.checkpoint import (
            save_checkpoint, load_checkpoint,
            list_checkpoints, delete_checkpoint,
        )
        assert callable(save_checkpoint)
        assert callable(load_checkpoint)
        assert callable(list_checkpoints)
        assert callable(delete_checkpoint)

    def test_save_and_load(self, data_dir):
        """Save a checkpoint and load it back."""
        from app.checkpoint import save_checkpoint, load_checkpoint

        cp = save_checkpoint(
            data_dir, "task-001",
            data={"content": "test", "steps": [1, 2, 3]},
            step_index=2,
        )
        assert cp.task_id == "task-001"
        assert cp.data["content"] == "test"
        assert cp.step_index == 2

        loaded = load_checkpoint(data_dir, "task-001")
        assert loaded is not None
        assert loaded.task_id == "task-001"
        assert loaded.data["content"] == "test"
        assert loaded.step_index == 2

    def test_load_nonexistent(self, data_dir):
        """Loading a nonexistent checkpoint should return None."""
        from app.checkpoint import load_checkpoint
        assert load_checkpoint(data_dir, "nonexistent") is None

    def test_list_checkpoints(self, data_dir):
        """List should return all checkpoint IDs."""
        from app.checkpoint import save_checkpoint, list_checkpoints

        save_checkpoint(data_dir, "task-a", data={})
        save_checkpoint(data_dir, "task-b", data={})
        save_checkpoint(data_dir, "task-c", data={})

        cps = list_checkpoints(data_dir)
        assert set(cps) == {"task-a", "task-b", "task-c"}

    def test_list_empty(self, data_dir):
        """List should return empty list when no checkpoints."""
        from app.checkpoint import list_checkpoints
        assert list_checkpoints(data_dir) == []

    def test_delete_checkpoint(self, data_dir):
        """Delete should remove the checkpoint file."""
        from app.checkpoint import (
            save_checkpoint, load_checkpoint,
            delete_checkpoint,
        )

        save_checkpoint(data_dir, "task-001", data={})
        assert load_checkpoint(data_dir, "task-001") is not None

        result = delete_checkpoint(data_dir, "task-001")
        assert result is True
        assert load_checkpoint(data_dir, "task-001") is None

    def test_delete_nonexistent(self, data_dir):
        """Deleting a nonexistent checkpoint should return False."""
        from app.checkpoint import delete_checkpoint
        assert delete_checkpoint(data_dir, "nonexistent") is False

    def test_overwrite_checkpoint(self, data_dir):
        """Saving twice should overwrite."""
        from app.checkpoint import save_checkpoint, load_checkpoint

        save_checkpoint(data_dir, "task-001", data={"v": 1}, step_index=1)
        save_checkpoint(data_dir, "task-001", data={"v": 2}, step_index=5)

        loaded = load_checkpoint(data_dir, "task-001")
        assert loaded.data["v"] == 2
        assert loaded.step_index == 5

    def test_checkpoint_file_format(self, data_dir):
        """Checkpoint JSON should be valid with all fields."""
        from app.checkpoint import save_checkpoint, _get_checkpoint_path

        save_checkpoint(data_dir, "task-001", data={"key": "value"})
        path = _get_checkpoint_path(data_dir, "task-001")

        with open(path) as f:
            raw = json.load(f)

        assert "task_id" in raw
        assert "data" in raw
        assert "saved_at" in raw
        assert "step_index" in raw
        assert raw["task_id"] == "task-001"
        assert raw["data"] == {"key": "value"}

    def test_save_complex_data(self, data_dir):
        """Checkpoint should handle complex nested data."""
        from app.checkpoint import save_checkpoint, load_checkpoint

        complex_data = {
            "steps": [{"id": 1, "status": "done"}, {"id": 2, "status": "pending"}],
            "config": {"retry": 3, "timeout": 30},
            "results": ["a", "b", "c"],
        }
        save_checkpoint(data_dir, "task-001", data=complex_data)

        loaded = load_checkpoint(data_dir, "task-001")
        assert loaded.data == complex_data

    @pytest.mark.asyncio
    async def test_checkpoint_integration_with_task_manager(self):
        """After update_progress, a checkpoint should be saved."""
        import tempfile
        from pathlib import Path
        from app.task_manager import TaskManager
        from app.checkpoint import load_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir)

            tm = TaskManager(tasks_dir=Path(tmpdir))
            tm.data_dir = data_dir  # Set data_dir for checkpoint

            task = tm.create(content="test task")
            tm.update_progress(task.task_id, 50, "half done")

            cp = load_checkpoint(data_dir, task.task_id)
            assert cp is not None
            assert cp.data["progress"] == 50
            assert cp.data["current_step"] == "half done"
