"""Tests for app.task_planner module - plan_task, step management, parallel execution."""
import asyncio
import pytest


class TestPlanTask:
    """Tests for plan_task tool and step management."""

    @pytest.mark.asyncio
    async def test_plan_task_creates_steps(self):
        """plan_task should create a plan with correct number of steps."""
        from app.task_planner import plan_task, get_plan

        chunks = []
        async for chunk in plan_task("test goal", ["step1", "step2", "step3"]):
            chunks.append(chunk)

        assert len(chunks) == 1
        plan = get_plan(chunks[0].id)
        assert plan is not None
        assert plan.goal == "test goal"
        assert len(plan.steps) == 3
        for step in plan.steps:
            assert step.status == "pending"

    @pytest.mark.asyncio
    async def test_plan_task_empty_subtasks(self):
        """plan_task with empty subtasks should still work."""
        from app.task_planner import plan_task, get_plan

        chunks = []
        async for chunk in plan_task("solo goal", []):
            chunks.append(chunk)

        plan = get_plan(chunks[0].id)
        assert plan.goal == "solo goal"
        assert len(plan.steps) == 0

    def test_mark_step_complete(self):
        """mark_step_complete should update status and return next step."""
        from app.task_planner import plan_task, mark_step_complete, get_next_pending_step
        import asyncio as aio

        async def _run():
            chunks = []
            async for chunk in plan_task("goal", ["a", "b", "c"]):
                chunks.append(chunk)
            return chunks[0].id

        task_id = aio.run(_run())

        next_step = mark_step_complete(task_id, 0, "done a")
        assert next_step == "b"

        next_step = mark_step_complete(task_id, 1, "done b")
        assert next_step == "c"

        next_step = mark_step_complete(task_id, 2, "done c")
        assert next_step is None  # All done

    def test_get_next_pending_step(self):
        """get_next_pending_step should return the first pending step."""
        from app.task_planner import plan_task, get_next_pending_step, mark_step_complete
        import asyncio as aio

        async def _run():
            chunks = []
            async for chunk in plan_task("goal", ["a", "b", "c"]):
                chunks.append(chunk)
            return chunks[0].id

        task_id = aio.run(_run())

        assert get_next_pending_step(task_id) == "a"
        mark_step_complete(task_id, 0)
        assert get_next_pending_step(task_id) == "b"
        mark_step_complete(task_id, 1)
        assert get_next_pending_step(task_id) == "c"

    def test_get_plan_nonexistent(self):
        """get_plan for nonexistent task should return None."""
        from app.task_planner import get_plan
        assert get_plan("nonexistent") is None


class TestParallelExecution:
    """Tests for execute_parallel, execute_sequential, execute_mixed."""

    @pytest.mark.asyncio
    async def test_execute_sequential(self):
        """execute_sequential should run steps one at a time."""
        from app.task_planner import (
            PlanStep, execute_sequential,
        )

        steps = [
            PlanStep(step_id="s1", description="step 1"),
            PlanStep(step_id="s2", description="step 2"),
            PlanStep(step_id="s3", description="step 3"),
        ]
        order = []

        async def executor(step):
            order.append(step.step_id)
            await asyncio.sleep(0.01)
            return f"done {step.step_id}"

        results = await execute_sequential(steps, executor)
        assert results == ["done s1", "done s2", "done s3"]
        assert order == ["s1", "s2", "s3"]  # Sequential
        for step in steps:
            assert step.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_parallel(self):
        """execute_parallel should run all steps concurrently."""
        from app.task_planner import (
            PlanStep, execute_parallel,
        )

        steps = [
            PlanStep(step_id="p1", description="step 1"),
            PlanStep(step_id="p2", description="step 2"),
            PlanStep(step_id="p3", description="step 3"),
        ]
        start_times = []
        end_times = []

        async def executor(step):
            start_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.02)
            end_times.append(asyncio.get_event_loop().time())
            return f"done {step.step_id}"

        results = await execute_parallel(steps, executor)
        assert len(results) == 3
        # All should start before any finishes (parallel execution)
        assert max(start_times) < min(end_times) + 0.01  # tolerance
        for step in steps:
            assert step.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_parallel_with_failure(self):
        """execute_parallel should handle failures, marking steps as failed."""
        from app.task_planner import (
            PlanStep, execute_parallel,
        )

        steps = [
            PlanStep(step_id="ok", description="good"),
            PlanStep(step_id="fail", description="bad"),
        ]

        async def executor(step):
            if step.step_id == "fail":
                raise ValueError("intentional failure")
            return "ok"

        results = await execute_parallel(steps, executor)
        assert results[0] == "ok"
        assert "FAILED" in results[1]
        assert steps[0].status == "completed"
        assert steps[1].status == "failed"

    @pytest.mark.asyncio
    async def test_execute_mixed_with_dependencies(self):
        """execute_mixed should respect depends_on."""
        from app.task_planner import (
            PlanStep, execute_mixed,
        )

        steps = [
            PlanStep(step_id="a", description="step a"),
            PlanStep(step_id="b", description="step b", depends_on=["a"]),
            PlanStep(step_id="c", description="step c", depends_on=["b"]),
        ]
        order = []

        async def executor(step):
            order.append(step.step_id)
            await asyncio.sleep(0.01)
            return f"done {step.step_id}"

        results = await execute_mixed(steps, executor)
        assert results == ["done a", "done b", "done c"]
        # a must be first, b before c
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")
        for step in steps:
            assert step.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_mixed_independent_parallel(self):
        """Independent steps in execute_mixed should run in parallel."""
        from app.task_planner import (
            PlanStep, execute_mixed,
        )
        import time

        steps = [
            PlanStep(step_id="x", description="independent x"),
            PlanStep(step_id="y", description="independent y"),
        ]
        start_times = []

        async def executor(step):
            start_times.append(time.monotonic())
            await asyncio.sleep(0.02)
            return f"done {step.step_id}"

        results = await execute_mixed(steps, executor)
        # Independent steps should start nearly simultaneously
        assert abs(start_times[0] - start_times[1]) < 0.05

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        """Progress callback should be called with correct counts."""
        from app.task_planner import (
            PlanStep, execute_sequential,
        )

        steps = [
            PlanStep(step_id="s1", description="step 1"),
            PlanStep(step_id="s2", description="step 2"),
        ]
        progress_calls = []

        def on_progress(count, desc):
            progress_calls.append((count, desc))

        async def executor(step):
            return f"done {step.step_id}"

        await execute_sequential(steps, executor, progress_callback=on_progress)
        assert progress_calls == [(1, "step 1"), (2, "step 2")]
