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


class TaskManager:
    """Manages async task lifecycle with JSON file persistence."""

    def __init__(self, tasks_dir: Path | None = None) -> None:
        self.tasks_dir = tasks_dir or TASKS_DIR
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

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
        tasks = []
        for path in sorted(
            self.tasks_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            data = json.loads(path.read_text(encoding="utf-8"))
            tasks.append(TaskRecord(**data))
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

    # ---- Execution ----

    async def execute(self, task: TaskRecord, agent: "Agent") -> None:
        """Run a task in the background, updating status on completion.

        Args:
            task: The TaskRecord to execute.
            agent: The Agent instance to use for processing.
        """
        from agentscope.message import UserMsg

        self.update(task.task_id, status="running", started_at=_now())

        try:
            reply = await agent.reply(UserMsg("user", task.content))
            self.update(
                task.task_id,
                status="completed",
                completed_at=_now(),
                result=str(reply),
            )
        except Exception as e:
            self.update(
                task.task_id,
                status="failed",
                completed_at=_now(),
                error=str(e),
            )

    def start_execute(self, task: TaskRecord, agent: "Agent") -> None:
        """Start background execution without awaiting.

        Args:
            task: The TaskRecord to execute.
            agent: The Agent instance to use for processing.
        """
        asyncio.create_task(self.execute(task, agent))