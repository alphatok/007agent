"""Tests for app.task_manager module."""
import json
import tempfile
from pathlib import Path

import pytest


class TestTaskManager:
    """Tests for TaskManager CRUD and persistence."""

    @pytest.fixture
    def tm(self) -> "TaskManager":
        """Create a TaskManager with a temp directory."""
        from app.task_manager import TaskManager

        with tempfile.TemporaryDirectory() as tmpdir:
            yield TaskManager(tasks_dir=Path(tmpdir))

    def test_create_task(self, tm: "TaskManager") -> None:
        """create should return a TaskRecord with task_id."""
        from app.task_manager import TaskRecord

        task = tm.create(content="Hello, world!")
        assert isinstance(task, TaskRecord)
        assert task.task_id
        assert len(task.task_id) == 12
        assert task.status == "pending"
        assert task.content == "Hello, world!"
        assert task.subagent is None

    def test_create_task_with_subagent(self, tm: "TaskManager") -> None:
        """create should accept subagent parameter."""
        task = tm.create(content="Test", subagent="code-reviewer")
        assert task.subagent == "code-reviewer"

    def test_get_task(self, tm: "TaskManager") -> None:
        """get should return the task by ID."""
        task = tm.create(content="Test")
        fetched = tm.get(task.task_id)
        assert fetched is not None
        assert fetched.task_id == task.task_id
        assert fetched.content == "Test"

    def test_get_nonexistent_task(self, tm: "TaskManager") -> None:
        """get should return None for nonexistent task."""
        assert tm.get("nonexistent") is None

    def test_list_tasks(self, tm: "TaskManager") -> None:
        """list_all should return all tasks, newest first."""
        tm.create(content="Task 1")
        tm.create(content="Task 2")
        tasks = tm.list_all()
        assert len(tasks) == 2
        # Newest first
        assert tasks[0].content == "Task 2"
        assert tasks[1].content == "Task 1"

    def test_delete_task(self, tm: "TaskManager") -> None:
        """delete should remove the task file."""
        task = tm.create(content="Test")
        assert tm.delete(task.task_id) is True
        assert tm.get(task.task_id) is None

    def test_delete_nonexistent_task(self, tm: "TaskManager") -> None:
        """delete should return False for nonexistent task."""
        assert tm.delete("nonexistent") is False

    def test_update_task(self, tm: "TaskManager") -> None:
        """update should modify task fields and persist."""
        task = tm.create(content="Test")
        updated = tm.update(task.task_id, status="running", result="OK")
        assert updated is not None
        assert updated.status == "running"
        assert updated.result == "OK"

    def test_update_nonexistent_task(self, tm: "TaskManager") -> None:
        """update should return None for nonexistent task."""
        assert tm.update("nonexistent", status="running") is None

    def test_task_state_transitions(self, tm: "TaskManager") -> None:
        """Task should follow pending -> running -> completed flow."""
        from app.task_manager import _now

        task = tm.create(content="Test")
        assert task.status == "pending"

        tm.update(task.task_id, status="running", started_at=_now())
        task = tm.get(task.task_id)
        assert task is not None
        assert task.status == "running"
        assert task.started_at is not None

        tm.update(task.task_id, status="completed", completed_at=_now(),
                  result="Done")
        task = tm.get(task.task_id)
        assert task is not None
        assert task.status == "completed"
        assert task.completed_at is not None
        assert task.result == "Done"

    def test_task_persistence(self, tm: "TaskManager") -> None:
        """Task data should persist to JSON file."""
        task = tm.create(content="Persist me")
        # Read the JSON file directly
        path = tm._path(task.task_id)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["task_id"] == task.task_id
        assert data["status"] == "pending"
        assert data["content"] == "Persist me"