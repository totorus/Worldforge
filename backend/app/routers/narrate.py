"""Narration router — runs the narrative enrichment pipeline on simulated worlds."""

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
from app.narrator.pipeline import run_narration, run_partial_narration, ALL_STEPS

logger = logging.getLogger("worldforge.narrate")

router = APIRouter()

# Step labels for progress reporting
_STEP_LABELS = {
    0: "Découpage en ères",
    1: "Nommage",
    2: "Fiches de factions",
    3: "Fiches de régions",
    4: "Narration des événements",
    5: "Biographies des personnages",
    6: "Légendes",
    7: "Extraction d'entités",
    8: "Vérification de cohérence",
}


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


def _check_world_ready(world: World) -> None:
    """Verify the world is in a valid state for narration."""
    if world.status not in ("simulated", "narrated"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le monde doit être simulé avant la narration (statut actuel : {world.status})",
        )
    if not world.config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Le monde n'a pas de configuration",
        )
    if not world.timeline:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Le monde n'a pas de timeline — lancez d'abord une simulation",
        )


class PartialNarrationRequest(BaseModel):
    steps: list[str]


async def _run_narration_background(task_id: str, world_id: str, config: dict, timeline: dict):
    """Background coroutine for full narration with step-by-step progress."""
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=5, message="Démarrage de la narration")

        # We use run_narration but report progress after each step via a wrapper.
        # Since run_narration is sequential, we run partial steps one-by-one for progress.
        from app.narrator.pipeline import (
            _run_era_splitting, _run_naming, _run_faction_sheets,
            _run_region_sheets, _run_event_narratives, _run_character_bios,
            _run_legends, _run_entity_extraction, run_coherence_with_fix,
        )

        narrative_blocks: dict = {}
        total_steps = 9

        step_runners = [
            ("eras", lambda: _run_era_splitting(config, timeline)),
            ("names", lambda: _run_naming(config, timeline)),
            ("factions", lambda: _run_faction_sheets(config, timeline)),
            ("regions", lambda: _run_region_sheets(config, timeline)),
            ("events", lambda: _run_event_narratives(config, timeline, narrative_blocks)),
            ("characters", lambda: _run_character_bios(config, timeline, narrative_blocks)),
            ("legends", lambda: _run_legends(config, narrative_blocks)),
            ("entity_summary", lambda: _run_entity_extraction(config, narrative_blocks)),
            ("coherence_report", lambda: run_coherence_with_fix(config, narrative_blocks)),
        ]

        for i, (key, runner) in enumerate(step_runners):
            progress = int(10 + (80 * i / total_steps))
            await update_task(task_id, progress=progress, message=f"Étape {i+1}/{total_steps} : {_STEP_LABELS.get(i, key)}")
            narrative_blocks[key] = await runner()

        await update_task(task_id, progress=95, message="Sauvegarde des résultats…")

        # Save to DB
        async with async_session() as db:
            result = await db.execute(select(World).where(World.id == world_id))
            world = result.scalar_one_or_none()
            if not world:
                await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
                return

            world.narrative_blocks = narrative_blocks
            world.status = "narrated"
            await db.commit()

        score = narrative_blocks.get("coherence_report", {}).get("score")
        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Narration terminée",
            result={
                "world_id": world_id,
                "coherence_score": score,
            },
        )
    except Exception as exc:
        logger.exception("Narration background task failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))


async def _run_partial_narration_background(
    task_id: str, world_id: str, config: dict, timeline: dict,
    steps: list[str], existing_blocks: dict,
):
    """Background coroutine for partial narration."""
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Narration partielle en cours…")

        narrative_blocks = await run_partial_narration(config, timeline, steps, existing_blocks)

        await update_task(task_id, progress=90, message="Sauvegarde…")

        async with async_session() as db:
            result = await db.execute(select(World).where(World.id == world_id))
            world = result.scalar_one_or_none()
            if not world:
                await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
                return

            world.narrative_blocks = narrative_blocks
            if world.status == "simulated":
                world.status = "narrated"
            await db.commit()

        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Narration partielle terminée",
            result={"world_id": world_id, "steps_executed": steps},
        )
    except Exception as exc:
        logger.exception("Partial narration background task failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))


@router.post("/{world_id}")
async def run_full_narration(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run the full narration pipeline on a simulated world (background task).

    Generates all narrative blocks: eras, names, factions, regions,
    events, characters, legends, and coherence report.
    """
    world = await _get_user_world(world_id, db, user)
    _check_world_ready(world)

    task = create_task(type="narration", world_id=str(world.id), user_id=str(user.id))
    asyncio.create_task(
        _run_narration_background(task.id, str(world.id), world.config, world.timeline)
    )

    return {
        "task_id": task.id,
        "world_id": str(world.id),
        "status": "accepted",
        "message": "Narration lancée en arrière-plan",
    }


@router.post("/{world_id}/partial")
async def run_partial(
    world_id: UUID,
    body: PartialNarrationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run specific narration steps on a simulated world (background task).

    Accepts a list of step names in the body. Valid steps:
    era_splitting, naming, faction_sheets, region_sheets,
    event_narratives, character_bios, legends, coherence_check
    """
    world = await _get_user_world(world_id, db, user)
    _check_world_ready(world)

    # Validate step names
    invalid_steps = [s for s in body.steps if s not in ALL_STEPS]
    if invalid_steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Étapes de narration invalides",
                "invalid_steps": invalid_steps,
                "valid_steps": ALL_STEPS,
            },
        )

    existing_blocks = world.narrative_blocks or {}

    task = create_task(type="narration_partial", world_id=str(world.id), user_id=str(user.id))
    asyncio.create_task(
        _run_partial_narration_background(
            task.id, str(world.id), world.config, world.timeline,
            body.steps, existing_blocks,
        )
    )

    return {
        "task_id": task.id,
        "world_id": str(world.id),
        "status": "accepted",
        "steps": body.steps,
        "message": "Narration partielle lancée en arrière-plan",
    }


@router.get("/{world_id}/status")
async def narration_status(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return narration status and available blocks for a world."""
    world = await _get_user_world(world_id, db, user)

    blocks = world.narrative_blocks or {}
    available_blocks = [key for key in blocks if blocks[key]]

    return {
        "world_id": str(world.id),
        "status": world.status,
        "has_narrative": world.status in ("narrated",),
        "available_blocks": available_blocks,
        "coherence_score": blocks.get("coherence_report", {}).get("score") if blocks else None,
        "steps": ALL_STEPS,
    }


@router.get("/{world_id}/blocks")
async def get_narrative_blocks(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all narrative blocks for a world."""
    world = await _get_user_world(world_id, db, user)

    if not world.narrative_blocks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucun contenu narratif disponible — lancez d'abord la narration",
        )

    return {
        "world_id": str(world.id),
        "narrative_blocks": world.narrative_blocks,
    }
