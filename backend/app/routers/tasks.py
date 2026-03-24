"""Tasks router — query background task status."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import User
from app.services.auth import get_current_user
from app.services.task_manager import get_task, get_user_tasks

router = APIRouter()


@router.get("/")
async def list_tasks(user: User = Depends(get_current_user)):
    """List all tasks for the current user."""
    tasks = get_user_tasks(str(user.id))
    return {
        "tasks": [
            {
                "task_id": t.id,
                "type": t.type,
                "world_id": t.world_id,
                "status": t.status.value,
                "progress": t.progress,
                "message": t.message,
                "error": t.error,
            }
            for t in tasks
        ]
    }


@router.get("/{task_id}")
async def task_status(task_id: str, user: User = Depends(get_current_user)):
    """Get status of a specific task."""
    task = get_task(task_id)
    if not task or task.user_id != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tâche introuvable",
        )
    return {
        "task_id": task.id,
        "type": task.type,
        "world_id": task.world_id,
        "status": task.status.value,
        "progress": task.progress,
        "message": task.message,
        "result": task.result,
        "error": task.error,
    }
