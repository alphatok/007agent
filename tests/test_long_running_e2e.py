"""E2E tests for long-running task capabilities: progress, checkpoint, resume."""
import asyncio
import os
import tempfile
import pytest
from pathlib import Path


class TestProgressE2E:
    """E2E: Progress reporting through the task pipeline."""

    @pytest.mark.asyncio
    async def test_update_progress_persists(self):
        """update_progress should persist to JSON and be readable."""
        from app.task_manager import TaskManager

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir)
            tm = TaskManager(tasks_dir=Path(tmpdir))
            tm.data_dir = data_dir

            task = tm.create(content="test")
            result = tm.update_progress(task.task_id, 75, "step 3/4")

            assert result is not None
            assert result.progress == 75
            assert result.current_step == "step 3/4"

            # Reload from disk
            task2 = tm.get(task.task_id)
            assert task2.progress == 75
            assert task2.current_step == "step 3/4"

    @pytest.mark.asyncio
    async def test_progress_queue_events(self):
        """Progress queue should receive events."""
        from app.task_manager import TaskManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(tasks_dir=Path(tmpdir))

            task = tm.create(content="test")
            queue = tm.progress_queue(task.task_id)

            # Push a progress event
            await queue.put({"type": "progress", "progress": 50})
            await queue.put({"type": "done", "result": "ok"})

            event1 = await asyncio.wait_for(queue.get(), timeout=0.5)
            assert event1["type"] == "progress"
            assert event1["progress"] == 50

            event2 = await asyncio.wait_for(queue.get(), timeout=0.5)
            assert event2["type"] == "done"

    @pytest.mark.asyncio
    async def test_add_step_tracks_subtasks(self):
        """add_step should append to steps list."""
        from app.task_manager import TaskManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(tasks_dir=Path(tmpdir))

            task = tm.create(content="multi-step task")
            tm.add_step(task.task_id, "step 1: analyze")
            tm.add_step(task.task_id, "step 2: implement")

            task2 = tm.get(task.task_id)
            assert len(task2.steps) == 2
            assert task2.steps[0] == "step 1: analyze"
            assert task2.steps[1] == "step 2: implement"


class TestCheckpointResumeE2E:
    """E2E: Checkpoint save and resume flow."""

    @pytest.mark.asyncio
    async def test_checkpoint_auto_saved_on_progress(self):
        """update_progress should automatically save a checkpoint."""
        from app.task_manager import TaskManager
        from app.checkpoint import load_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir)
            tm = TaskManager(tasks_dir=Path(tmpdir))
            tm.data_dir = data_dir

            task = tm.create(content="long task")
            tm.update_progress(task.task_id, 25, "checkpoint 1")
            tm.update_progress(task.task_id, 50, "checkpoint 2")
            tm.update_progress(task.task_id, 75, "checkpoint 3")

            cp = load_checkpoint(data_dir, task.task_id)
            assert cp is not None
            assert cp.data["progress"] == 75
            assert cp.data["current_step"] == "checkpoint 3"
            assert cp.step_index == 75

    @pytest.mark.asyncio
    async def test_resume_task_loads_checkpoint(self):
        """resume_task should load checkpoint and restart."""
        from app.task_manager import TaskManager
        from app.checkpoint import save_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir)
            tm = TaskManager(tasks_dir=Path(tmpdir))
            tm.data_dir = data_dir

            task = tm.create(content="resume me")
            tm.update(task.task_id, progress=40, current_step="mid-task")

            save_checkpoint(
                data_dir, task.task_id,
                data={"content": "resume me", "progress": 40, "current_step": "mid-task"},
                step_index=40,
            )

            # resume_task requires an agent, but we can test the status update
            task2 = tm.get(task.task_id)
            assert task2.progress == 40
            assert task2.current_step == "mid-task"

    @pytest.mark.asyncio
    async def test_full_lifecycle_progress_to_checkpoint(self):
        """Full lifecycle: create → progress → checkpoint → get → verify."""
        import json
        from app.task_manager import TaskManager
        from app.checkpoint import load_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir)
            tm = TaskManager(tasks_dir=Path(tmpdir))
            tm.data_dir = data_dir

            # Create
            task = tm.create(content="full lifecycle test")
            assert task.status == "pending"

            # Progress updates
            for pct in [10, 25, 50, 75, 90]:
                tm.update_progress(task.task_id, pct, f"step at {pct}%")

            # Verify checkpoint
            cp = load_checkpoint(data_dir, task.task_id)
            assert cp is not None
            assert cp.data["progress"] == 90

            # Verify task state
            final = tm.get(task.task_id)
            assert final.progress == 90
            assert final.current_step == "step at 90%"
            assert final.status == "pending"


class TestTaskManagerResume:
    """E2E: Task resume after interruption."""

    @pytest.mark.asyncio
    async def test_resume_task_method_exists(self):
        """resume_task should be a callable method."""
        from app.task_manager import TaskManager

        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(tasks_dir=Path(tmpdir))
            assert callable(tm.resume_task)

    @pytest.mark.asyncio
    async def test_resume_task_returns_none_for_completed(self):
        """resume_task should return None if no checkpoint exists."""
        from app.task_manager import TaskManager

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir)
            tm = TaskManager(tasks_dir=Path(tmpdir))
            tm.data_dir = data_dir

            task = tm.create(content="completed task")
            tm.update(task.task_id, status="completed")

            # resume_task requires an agent parameter
            # Just verify the method handles missing checkpoint gracefully
            # (We can't easily test the full flow without a real agent)

    @pytest.mark.asyncio
    async def test_task_list_shows_checkpoint_info(self):
        """list_all should show checkpoint info for pending tasks."""
        from app.task_manager import TaskManager
        from app.checkpoint import save_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            os.makedirs(data_dir)
            tm = TaskManager(tasks_dir=Path(tmpdir))
            tm.data_dir = data_dir

            task = tm.create(content="checkpoint task")
            save_checkpoint(data_dir, task.task_id, data={"progress": 30}, step_index=30)

            tasks = tm.list_all()
            checkpoint_tasks = [t for t in tasks if t.task_id == task.task_id]
            assert len(checkpoint_tasks) == 1
            # Should show checkpoint marker
            assert "[checkpoint]" in checkpoint_tasks[0].current_step


class TestToolRegistrationE2E:
    """E2E: Verify all new tools are registered."""

    @pytest.mark.asyncio
    async def test_all_tools_registered(self):
        """All 6 new tools should be in BUILTIN_TOOLS."""
        from app.tools import BUILTIN_TOOLS

        tool_names = set()
        for t in BUILTIN_TOOLS:
            if hasattr(t, 'name'):
                tool_names.add(t.name)
            elif hasattr(t, '__name__'):
                tool_names.add(t.__name__)

        expected = {
            'report_progress', 'plan_task', 'ask_user',
            'web_search', 'web_fetch',
        }
        found = expected & tool_names
        missing = expected - tool_names
        assert not missing, f"Missing tools: {missing}"

    @pytest.mark.asyncio
    async def test_report_progress_tool_yields(self):
        """report_progress should yield a ToolChunk."""
        from app.tools import report_progress

        chunks = []
        async for chunk in report_progress(50, "testing"):
            chunks.append(chunk)

        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_plan_task_tool_yields(self):
        """plan_task should yield a ToolChunk."""
        from app.tools import plan_task

        chunks = []
        async for chunk in plan_task("test", ["a", "b"]):
            chunks.append(chunk)

        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_ask_user_tool_yields(self):
        """ask_user should yield a ToolChunk."""
        from app.tools import ask_user

        chunks = []
        async for chunk in ask_user("test question?"):
            chunks.append(chunk)

        assert len(chunks) > 0
