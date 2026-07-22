"""Checkpoint save/load for task resumption."""
import json
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """A saved checkpoint for task resumption."""
    task_id: str
    data: dict[str, Any]
    saved_at: str = field(default_factory=lambda: datetime.now().isoformat())
    step_index: int = 0


def _get_checkpoint_dir(data_dir: str) -> str:
    """Get the checkpoint directory path."""
    d = os.path.join(data_dir, "checkpoints")
    os.makedirs(d, exist_ok=True)
    return d


def _get_checkpoint_path(data_dir: str, task_id: str) -> str:
    """Get the checkpoint file path for a task."""
    return os.path.join(_get_checkpoint_dir(data_dir), f"{task_id}.json")


def save_checkpoint(data_dir: str, task_id: str, data: dict[str, Any],
                    step_index: int = 0) -> Checkpoint:
    """Save a checkpoint for a task.
    
    Args:
        data_dir: Base data directory
        task_id: Task identifier
        data: Arbitrary data to save
        step_index: Current step index
        
    Returns:
        The saved Checkpoint object
    """
    checkpoint = Checkpoint(
        task_id=task_id,
        data=data,
        step_index=step_index,
    )
    path = _get_checkpoint_path(data_dir, task_id)
    with open(path, "w") as f:
        json.dump({
            "task_id": checkpoint.task_id,
            "data": checkpoint.data,
            "saved_at": checkpoint.saved_at,
            "step_index": checkpoint.step_index,
        }, f, indent=2, ensure_ascii=False)
    logger.info(f"Checkpoint saved: {task_id} (step {step_index})")
    return checkpoint


def load_checkpoint(data_dir: str, task_id: str) -> Checkpoint | None:
    """Load a checkpoint for a task.
    
    Args:
        data_dir: Base data directory
        task_id: Task identifier
        
    Returns:
        Checkpoint if found, None otherwise
    """
    path = _get_checkpoint_path(data_dir, task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            raw = json.load(f)
        return Checkpoint(
            task_id=raw["task_id"],
            data=raw["data"],
            saved_at=raw["saved_at"],
            step_index=raw.get("step_index", 0),
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to load checkpoint {task_id}: {e}")
        return None


def list_checkpoints(data_dir: str) -> list[str]:
    """List all task IDs with checkpoints."""
    d = _get_checkpoint_dir(data_dir)
    return [
        f.replace(".json", "")
        for f in os.listdir(d)
        if f.endswith(".json")
    ]


def delete_checkpoint(data_dir: str, task_id: str) -> bool:
    """Delete a checkpoint file."""
    path = _get_checkpoint_path(data_dir, task_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False