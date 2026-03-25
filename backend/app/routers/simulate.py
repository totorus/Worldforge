"""Simulate router — run and extend world simulations."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.user import User
from app.models.world import World
from app.services.auth import get_current_user
from app.services.task_manager import (
    TaskStatus,
    create_task,
    update_task,
)
from app.simulator.engine import run_simulation

logger = logging.getLogger("worldforge.simulate")

router = APIRouter()


class ExtendRequest(BaseModel):
    additional_years: int


async def _get_user_world(
    world_id: UUID,
    db: AsyncSession,
    user: User,
) -> World:
    """Fetch a world and verify it belongs to the current user."""
    result = await db.execute(
        select(World).where(World.id == world_id, World.user_id == user.id)
    )
    world = result.scalar_one_or_none()
    if not world:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monde introuvable ou accès refusé",
        )
    return world


def _count_events(timeline: dict) -> int:
    """Count total events across all ticks in a timeline."""
    total = 0
    for tick in timeline.get("ticks", []):
        total += len(tick.get("events", []))
    return total


async def _run_simulation_background(task_id: str, world_id: str, config: dict):
    """Background coroutine that runs the simulation and pushes progress."""
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Démarrage de la simulation")

        # Run the simulation (CPU-bound, run in executor)
        loop = asyncio.get_event_loop()
        await update_task(task_id, progress=20, message="Simulation en cours…")
        timeline = await loop.run_in_executor(None, run_simulation, config)

        await update_task(task_id, progress=80, message="Sauvegarde des résultats…")

        # Save results in a fresh DB session
        async with async_session() as db:
            result = await db.execute(select(World).where(World.id == world_id))
            world = result.scalar_one_or_none()
            if not world:
                await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
                return

            world.timeline = timeline
            world.status = "simulated"
            world.total_events = _count_events(timeline)
            world.simulation_years = config.get("meta", {}).get("simulation_years")
            await db.commit()

        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Simulation terminée",
            result={
                "world_id": world_id,
                "total_events": world.total_events,
                "total_ticks": len(timeline.get("ticks", [])),
            },
        )
    except Exception as exc:
        logger.exception("Simulation background task failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))


async def _extend_simulation_background(
    task_id: str,
    world_id: str,
    config: dict,
    additional_years: int,
    existing_ticks: list,
    last_world_state: dict,
):
    """Background coroutine that extends a simulation."""
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Préparation de l'extension")

        extended_config = dict(config)
        extended_config["meta"] = dict(extended_config["meta"])
        extended_config["meta"]["simulation_years"] = additional_years

        await update_task(task_id, progress=20, message="Extension de la simulation en cours…")
        loop = asyncio.get_event_loop()
        extension_timeline = await loop.run_in_executor(
            None, run_simulation, extended_config, last_world_state
        )

        await update_task(task_id, progress=80, message="Fusion et sauvegarde…")

        async with async_session() as db:
            result = await db.execute(select(World).where(World.id == world_id))
            world = result.scalar_one_or_none()
            if not world:
                await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
                return

            merged_timeline = dict(world.timeline or {})
            merged_timeline["ticks"] = existing_ticks + extension_timeline.get("ticks", [])

            world.timeline = merged_timeline
            world.status = "simulated"
            total_years = (world.simulation_years or 0) + additional_years
            world.simulation_years = total_years
            world.total_events = _count_events(merged_timeline)
            await db.commit()

        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Extension terminée",
            result={
                "world_id": world_id,
                "total_events": world.total_events,
                "total_ticks": len(merged_timeline.get("ticks", [])),
                "extended_by_years": additional_years,
            },
        )
    except Exception as exc:
        logger.exception("Extend simulation background task failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))


@router.post("/{world_id}")
async def simulate(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lance la simulation d'un monde configuré (tâche en arrière-plan)."""
    world = await _get_user_world(world_id, db, user)

    if not world.config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le monde n'a pas de configuration — configurez-le d'abord",
        )

    if world.status not in ("configured", "simulated", "narrated", "exported"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Le monde doit être configuré pour lancer une simulation (statut actuel : '{world.status}')",
        )

    task = create_task(type="simulation", world_id=str(world.id), user_id=str(user.id))
    asyncio.create_task(_run_simulation_background(task.id, str(world.id), world.config))

    return {
        "task_id": task.id,
        "world_id": str(world.id),
        "status": "accepted",
        "message": "Simulation lancée en arrière-plan",
    }


@router.post("/{world_id}/extend")
async def extend_simulation(
    world_id: UUID,
    body: ExtendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Prolonge une simulation existante avec des années supplémentaires (tâche en arrière-plan)."""
    world = await _get_user_world(world_id, db, user)

    if not world.timeline or not world.config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le monde doit avoir une simulation existante pour être prolongé",
        )

    if world.status not in ("simulated", "narrated"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Le monde doit être au statut 'simulated' ou 'narrated' pour prolonger (statut actuel : '{world.status}')",
        )

    if body.additional_years <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nombre d'années supplémentaires doit être positif",
        )

    existing_ticks = world.timeline.get("ticks", [])
    if not existing_ticks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La timeline existante ne contient aucun tick",
        )

    last_world_state = existing_ticks[-1].get("world_state")
    if not last_world_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le dernier tick ne contient pas d'état du monde",
        )

    task = create_task(type="simulation_extend", world_id=str(world.id), user_id=str(user.id))
    asyncio.create_task(
        _extend_simulation_background(
            task.id, str(world.id), world.config, body.additional_years,
            existing_ticks, last_world_state,
        )
    )

    return {
        "task_id": task.id,
        "world_id": str(world.id),
        "status": "accepted",
        "message": f"Extension de {body.additional_years} ans lancée en arrière-plan",
    }


@router.get("/{world_id}/status")
async def simulation_status(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne le statut du monde et des statistiques de base."""
    world = await _get_user_world(world_id, db, user)
    return {
        "world_id": str(world.id),
        "name": world.name,
        "status": world.status,
        "simulation_years": world.simulation_years,
        "total_events": world.total_events,
        "total_factions": world.total_factions,
        "has_timeline": world.timeline is not None,
        "has_narrative": world.narrative_blocks is not None,
    }


@router.get("/{world_id}/timeline")
async def get_timeline(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne le JSON complet de la timeline."""
    world = await _get_user_world(world_id, db, user)
    if not world.timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune timeline disponible — lancez d'abord une simulation",
        )
    return {
        "world_id": str(world.id),
        "timeline": world.timeline,
    }
