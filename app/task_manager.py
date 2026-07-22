"""Async task manager for HTTP API task submission and tracking.

Tasks are stored as JSON files in ``data/tasks/`` directory.
Status machine: pending -> running -> completed/failed/cancelled
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.checkpoint import delete_checkpoint, load_checkpoint, save_checkpoint

if TYPE_CHECKING:
    from agentscope.agent import Agent

TASKS_DIR = Path("data/tasks")


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    """A single async task record."""

    task_id: str
    status: str  # pending | running | completed | failed | cancelled
    content: str
    subagent: str | None = None
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    completed_at: str | None = None
    result: str | None = None
    error: str | None = None
    progress: int = 0
    current_step: str = ""
    steps: list = field(default_factory=list)


class TaskManager:
    """Manages async task lifecycle with JSON file persistence."""

    def __init__(
        self, tasks_dir: Path | None = None, data_dir: str = "data",
    ) -> None:
        self.tasks_dir = tasks_dir or TASKS_DIR
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self._progress_queues: dict[str, asyncio.Queue] = {}
        """Per-task progress queues for SSE streaming."""

    # ---- File helpers ----

    def _path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def _save(self, task: TaskRecord) -> None:
        self._path(task.task_id).write_text(
            json.dumps(asdict(task), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load(self, task_id: str) -> TaskRecord | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return TaskRecord(**data)

    # ---- CRUD ----

    def create(self, content: str, subagent: str | None = None) -> TaskRecord:
        """Create a new pending task."""
        task = TaskRecord(
            task_id=uuid.uuid4().hex[:12],
            status="pending",
            content=content,
            subagent=subagent,
        )
        self._save(task)
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        """Get a task by ID."""
        return self._load(task_id)

    def list_all(self) -> list[TaskRecord]:
        """List all tasks, newest first."""
        from app.checkpoint import list_checkpoints

        tasks = []
        checkpoints = set(list_checkpoints(self.data_dir))
        for path in sorted(
            self.tasks_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            data = json.loads(path.read_text(encoding="utf-8"))
            task = TaskRecord(**data)
            if task.status == "pending" and task.task_id in checkpoints:
                task.current_step = "[checkpoint] " + task.current_step
            tasks.append(task)
        return tasks

    def update(self, task_id: str, **kwargs) -> TaskRecord | None:
        """Update task fields and persist."""
        task = self._load(task_id)
        if task is None:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self._save(task)
        return task

    def delete(self, task_id: str) -> bool:
        """Delete a task. Returns True if deleted, False if not found."""
        path = self._path(task_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ---- Progress ----

    def update_progress(
        self, task_id: str, progress: int, current_step: str
    ) -> TaskRecord | None:
        """Update task progress and current_step, persists to JSON and saves checkpoint."""
        task = self.update(
            task_id, progress=progress, current_step=current_step,
        )
        if task:
            # Save checkpoint with current state for resumption
            save_checkpoint(
                self.data_dir, task_id,
                data={
                    "content": task.content,
                    "subagent": task.subagent,
                    "progress": progress,
                    "current_step": current_step,
                    "steps": task.steps,
                },
                step_index=progress,
            )
        return task

    def add_step(self, task_id: str, step_desc: str) -> None:
        """Add a new step to the task's steps list."""
        task = self._load(task_id)
        if task is None:
            return
        task.steps.append(step_desc)
        self._save(task)

    def progress_queue(self, task_id: str) -> asyncio.Queue:
        """Get or create a progress queue for SSE streaming."""
        if task_id not in self._progress_queues:
            self._progress_queues[task_id] = asyncio.Queue()
        return self._progress_queues[task_id]

    def _cleanup_queue(self, task_id: str) -> None:
        """Remove the progress queue for a completed task."""
        self._progress_queues.pop(task_id, None)

    async def execute_parallel_steps(
        self,
        task_id: str,
        steps: list,
        executor: "callable",
    ) -> list[str]:
        """Execute steps in parallel using task_planner.execute_parallel.

        Pushes step-level progress events to the SSE queue with step_id.

        Args:
            task_id: The task ID for progress tracking.
            steps: List of PlanStep instances.
            executor: Async function that executes a single step.

        Returns:
            List of results in the same order as steps.
        """
        from app.task_planner import execute_parallel

        async def progress_fn(completed: int, desc: str) -> None:
            if task_id in self._progress_queues:
                await self._progress_queues[task_id].put({
                    "type": "progress",
                    "progress": completed,
                    "current_step": desc,
                })

        return await execute_parallel(steps, executor, progress_fn)

    # ---- Execution ----

    async def execute(
        self,
        task: TaskRecord,
        agent: "Agent",
        progress_callback: callable | None = None,
    ) -> None:
        """Run a task in the background, updating status on completion.

        Args:
            task: The TaskRecord to execute.
            agent: The Agent instance to use for processing.
            progress_callback: Optional callback called after each step.
                Signature: progress_callback(task, progress, current_step).
        """
        from agentscope.message import UserMsg

        self.update(task.task_id, status="running", started_at=_now())

        try:
            # Save initial checkpoint for resumption
            save_checkpoint(
                self.data_dir, task.task_id,
                data={
                    "content": task.content,
                    "subagent": task.subagent,
                    "progress": task.progress,
                    "current_step": task.current_step,
                    "steps": task.steps,
                },
                step_index=task.progress,
            )
            reply = await agent.reply(UserMsg("user", task.content))
            self.update(
                task.task_id,
                status="completed",
                completed_at=_now(),
                result=str(reply),
            )
            # Delete checkpoint on successful completion
            delete_checkpoint(self.data_dir, task.task_id)
            # Push done event to progress queue
            if task.task_id in self._progress_queues:
                await self._progress_queues[task.task_id].put({
                    "type": "done",
                    "result": str(reply),
                })
        except Exception as e:
            self.update(
                task.task_id,
                status="failed",
                completed_at=_now(),
                error=str(e),
            )
            # Push error event to progress queue
            if task.task_id in self._progress_queues:
                await self._progress_queues[task.task_id].put({
                    "type": "error",
                    "error": str(e),
                })
        finally:
            if progress_callback:
                progress_callback(task, 100, "completed")
            # Cleanup queue after a short delay to allow SSE to drain
            self._cleanup_queue(task.task_id)

    def start_execute(self, task: TaskRecord, agent: "Agent") -> None:
        """Start background execution without awaiting.

        Args:
            task: The TaskRecord to execute.
            agent: The Agent instance to use for processing.
        """
        asyncio.create_task(self.execute(task, agent))

    def resume_task(self, task_id: str, agent: "Agent") -> TaskRecord | None:
        """Resume a task from its last checkpoint.

        Loads the checkpoint and re-executes the task from the saved
        step_index. Returns the task record if a checkpoint was found
        and resumption was started, None otherwise.

        Args:
            task_id: The task ID to resume.
            agent: The Agent instance to use for processing.

        Returns:
            TaskRecord if resumed, None if no checkpoint found.
        """
        cp = load_checkpoint(self.data_dir, task_id)
        if cp is None:
            return None
        task = self.get(task_id)
        if task is None:
            return None
        # Restore task state from checkpoint
        self.update(
            task_id,
            progress=cp.data.get("progress", 0),
            current_step=cp.data.get("current_step", ""),
            steps=cp.data.get("steps", []),
        )
        self.start_execute(task, agent)
        return task