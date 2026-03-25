"""In-memory task manager for long-running background tasks with WebSocket notifications."""

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    id: str
    type: str  # "simulation", "narration", "export"
    world_id: str
    user_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    message: str = ""
    result: Any = None
    error: str | None = None


# Global registry
_tasks: dict[str, TaskInfo] = {}
_subscribers: dict[str, list[asyncio.Queue]] = {}  # user_id -> list of queues


def create_task(type: str, world_id: str, user_id: str) -> TaskInfo:
    task = TaskInfo(
        id=str(uuid.uuid4()),
        type=type,
        world_id=world_id,
        user_id=user_id,
    )
    _tasks[task.id] = task
    return task


def get_task(task_id: str) -> TaskInfo | None:
    return _tasks.get(task_id)


def get_user_tasks(user_id: str) -> list[TaskInfo]:
    return [t for t in _tasks.values() if t.user_id == user_id]


async def update_task(
    task_id: str,
    status: TaskStatus | None = None,
    progress: int | None = None,
    message: str | None = None,
    result: Any = None,
    error: str | None = None,
):
    task = _tasks.get(task_id)
    if not task:
        return
    if status is not None:
        task.status = status
    if progress is not None:
        task.progress = progress
    if message is not None:
        task.message = message
    if result is not None:
        task.result = result
    if error is not None:
        task.error = error
    # Notify all WebSocket subscribers for this user
    await _notify(task.user_id, {
        "type": "task_update",
        "task_id": task.id,
        "task_type": task.type,
        "world_id": task.world_id,
        "status": task.status.value,
        "progress": task.progress,
        "message": task.message,
        "error": task.error,
    })


def subscribe(user_id: str) -> asyncio.Queue:
    if user_id not in _subscribers:
        _subscribers[user_id] = []
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[user_id].append(q)
    return q


def unsubscribe(user_id: str, q: asyncio.Queue):
    if user_id in _subscribers:
        _subscribers[user_id] = [x for x in _subscribers[user_id] if x is not q]
        if not _subscribers[user_id]:
            del _subscribers[user_id]


async def _notify(user_id: str, data: dict):
    for q in _subscribers.get(user_id, []):
        await q.put(data)


async def wizard_notify(user_id: str, event_type: str, data: dict):
    """Send a wizard-specific event to the user's WebSocket subscribers."""
    payload = {"type": event_type, **data}
    await _notify(user_id, payload)
