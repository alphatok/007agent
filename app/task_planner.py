"""Task planning and subtask management for long-running tasks."""
import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator, Awaitable, Callable
import uuid

from agentscope.tool import ToolChunk
from agentscope.message import TextBlock, ToolResultState


@dataclass
class PlanStep:
    """A single step in a task plan."""
    step_id: str
    description: str
    status: str = "pending"  # pending, running, completed, failed
    result: str = ""
    depends_on: list[str] = field(default_factory=list)  # IDs of steps this depends on


@dataclass
class TaskPlan:
    """A task plan with multiple steps."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_index: int = 0


# In-memory store for task plans (keyed by task_id)
_plans: dict[str, TaskPlan] = {}


async def plan_task(
    goal: str,
    subtasks: list[str],
    task_id: str = "",
) -> AsyncGenerator[ToolChunk, None]:
    """Create a task plan with subtasks.
    
    Use this when working on complex, multi-step tasks to break down
    the work into trackable subtasks.
    
    Args:
        goal: The overall goal of the task
        subtasks: List of subtask descriptions
        task_id: Optional task ID to associate the plan with
    """
    task_id = task_id or str(uuid.uuid4())
    steps = [
        PlanStep(
            step_id=f"{task_id}-step-{i}",
            description=desc,
        )
        for i, desc in enumerate(subtasks)
    ]
    plan = TaskPlan(goal=goal, steps=steps)
    _plans[task_id] = plan
    
    steps_text = "\n".join(
        f"  {i+1}. [{s.status}] {s.description}"
        for i, s in enumerate(steps)
    )
    yield ToolChunk(
        task_id=task_id,
        state=ToolResultState.SUCCESS,
        content=[TextBlock(text=f"Plan created for: {goal}\n{steps_text}")],
        metadata={"plan": {"goal": goal, "steps": [s.__dict__ for s in steps]}},
    )


def mark_step_complete(task_id: str, step_index: int, result: str = "") -> str | None:
    """Mark a step as completed and return the next pending step description."""
    plan = _plans.get(task_id)
    if not plan or step_index >= len(plan.steps):
        return None
    plan.steps[step_index].status = "completed"
    plan.steps[step_index].result = result
    plan.current_index = step_index + 1
    return get_next_pending_step(task_id)


def get_next_pending_step(task_id: str) -> str | None:
    """Get the next pending step description, or None if all done."""
    plan = _plans.get(task_id)
    if not plan:
        return None
    for step in plan.steps:
        if step.status == "pending":
            return step.description
    return None


def get_plan(task_id: str) -> TaskPlan | None:
    """Get the task plan for a task_id."""
    return _plans.get(task_id)


async def execute_parallel(
    steps: list[PlanStep],
    executor: Callable[[PlanStep], Awaitable[str]],
    progress_callback: Callable[[int, str], None] | None = None,
) -> list[str]:
    """Execute independent steps in parallel.

    Args:
        steps: List of plan steps to execute
        executor: Async function that executes a single step and returns result
        progress_callback: Called with (completed_count, total_count) after each step

    Returns:
        List of results in the same order as steps
    """
    async def execute_step(step: PlanStep, index: int) -> str:
        step.status = "running"
        try:
            result = await executor(step)
            step.status = "completed"
            step.result = result
            return result
        except Exception as e:
            step.status = "failed"
            step.result = str(e)
            return f"FAILED: {e}"

    tasks = [execute_step(step, i) for i, step in enumerate(steps)]
    results = await asyncio.gather(*tasks)
    return list(results)


async def execute_sequential(
    steps: list[PlanStep],
    executor: Callable[[PlanStep], Awaitable[str]],
    progress_callback: Callable[[int, str], None] | None = None,
) -> list[str]:
    """Execute steps one at a time in order.

    Args:
        steps: List of plan steps to execute
        executor: Async function that executes a single step and returns result
        progress_callback: Called with (completed_count, total_count) after each step

    Returns:
        List of results in the same order as steps
    """
    results = []
    for i, step in enumerate(steps):
        step.status = "running"
        if progress_callback:
            progress_callback(i + 1, step.description)
        try:
            result = await executor(step)
            step.status = "completed"
            step.result = result
            results.append(result)
        except Exception as e:
            step.status = "failed"
            step.result = str(e)
            results.append(f"FAILED: {e}")
    return results


async def execute_mixed(
    steps: list[PlanStep],
    executor: Callable[[PlanStep], Awaitable[str]],
    progress_callback: Callable[[int, str], None] | None = None,
) -> list[str]:
    """Execute steps respecting dependencies using topological order.

    Independent steps run in parallel; dependent steps wait for their
    prerequisites to complete.

    Args:
        steps: List of plan steps with depends_on relationships
        executor: Async function that executes a single step
        progress_callback: Called with (completed_count, total_count) after each step

    Returns:
        List of results in the same order as steps
    """
    results = [None] * len(steps)
    completed = set()

    # Build index: step_id -> index
    step_index = {s.step_id: i for i, s in enumerate(steps)}

    async def run_step(step: PlanStep, index: int):
        # Wait for dependencies
        for dep_id in step.depends_on:
            dep_idx = step_index.get(dep_id)
            if dep_idx is not None:
                while dep_idx not in completed:
                    await asyncio.sleep(0.1)

        step.status = "running"
        if progress_callback:
            progress_callback(len(completed) + 1, step.description)
        try:
            result = await executor(step)
            step.status = "completed"
            step.result = result
            results[index] = result
        except Exception as e:
            step.status = "failed"
            step.result = str(e)
            results[index] = f"FAILED: {e}"
        completed.add(index)

    # Start all steps; dependencies are handled internally
    tasks = [run_step(step, i) for i, step in enumerate(steps)]
    await asyncio.gather(*tasks)
    return results