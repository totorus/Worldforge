"""Narration router — runs the narrative enrichment pipeline on simulated worlds."""

import asyncio
import logging
import time
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
from app.narrator.schemas import validate_step_output

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


async def _save_narrative_blocks(world_id: str, narrative_blocks: dict, set_narrated: bool = False):
    """Persist narrative_blocks to DB (intermediate or final save)."""
    async with async_session() as db:
        result = await db.execute(select(World).where(World.id == world_id))
        world = result.scalar_one_or_none()
        if not world:
            return False
        world.narrative_blocks = narrative_blocks
        if set_narrated:
            world.status = "narrated"
        await db.commit()
    return True


async def _run_narration_background(task_id: str, world_id: str, config: dict, timeline: dict):
    """Background coroutine for full narration with step-by-step progress and intermediate saves."""
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=5, message="Démarrage de la narration")

        from app.narrator.pipeline import run_narration, validate_step_output
        from app.narrator.pipeline import (
            _run_era_splitting, _run_naming, _run_faction_sheets,
            _run_region_sheets, _run_event_narratives, _run_character_bios,
            _run_legends, _run_entity_extraction, run_coherence_with_fix,
        )
        from app.narrator.registry import EntityRegistry

        narrative_blocks: dict = {}
        run_report: dict = {"steps": {}, "pipeline_start": time.time()}
        total_steps = 9

        # Build entity registry from config and feed it after each step
        registry = EntityRegistry()
        registry.load_from_config(config)

        step_runners = [
            ("eras", lambda: _run_era_splitting(config, timeline)),
            ("names", lambda: _run_naming(config, timeline)),
            ("factions", lambda: _run_faction_sheets(config, timeline)),
            ("regions", lambda: _run_region_sheets(config, timeline)),
            ("events", lambda: _run_event_narratives(config, timeline, narrative_blocks, registry=registry)),
            ("characters", lambda: _run_character_bios(config, timeline, narrative_blocks, registry=registry)),  # eras+events passed inside _run_character_bios
            ("legends", lambda: _run_legends(config, narrative_blocks, registry=registry)),
            ("entity_summary", lambda: _run_entity_extraction(config, narrative_blocks, timeline)),
            ("coherence_report", lambda: run_coherence_with_fix(config, narrative_blocks, registry=registry)),
        ]

        for i, (key, runner) in enumerate(step_runners):
            progress = int(10 + (80 * i / total_steps))
            await update_task(task_id, progress=progress, message=f"Étape {i+1}/{total_steps} : {_STEP_LABELS.get(i, key)}")

            step_start = time.time()
            step_info = {"status": "running", "errors": []}

            try:
                result = await runner()
                validated, v_errors = validate_step_output(key, result)
                if v_errors:
                    for err in v_errors:
                        logger.warning(err)
                    step_info["validation_warnings"] = v_errors
                narrative_blocks[key] = validated
                step_info["status"] = "ok"
                item_count = len(validated) if isinstance(validated, (list, dict)) else 1
                step_info["items_produced"] = item_count
            except Exception as step_exc:
                logger.error("Step '%s' failed: %s", key, step_exc)
                narrative_blocks[key] = [] if key not in ("names", "coherence_report", "entity_summary") else {}
                step_info["status"] = "failed"
                step_info["errors"].append(f"{type(step_exc).__name__}: {str(step_exc)[:300]}")

            # Feed registry with step output
            registry.ingest_step(key, narrative_blocks.get(key))

            step_info["duration_s"] = round(time.time() - step_start, 1)
            run_report["steps"][key] = step_info

            # Intermediate save after each step
            await _save_narrative_blocks(world_id, narrative_blocks)

        # Finalize run report
        run_report["total_duration_s"] = round(time.time() - run_report["pipeline_start"], 1)
        del run_report["pipeline_start"]
        run_report["coherence_score"] = narrative_blocks.get("coherence_report", {}).get("score", 0)
        narrative_blocks["_run_report"] = run_report

        await update_task(task_id, progress=95, message="Sauvegarde finale…")

        # Final save with status change
        if not await _save_narrative_blocks(world_id, narrative_blocks, set_narrated=True):
            await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
            return

        score = narrative_blocks.get("coherence_report", {}).get("score")
        run_report = narrative_blocks.get("_run_report", {})
        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Narration terminée",
            result={
                "world_id": world_id,
                "coherence_score": score,
                "run_report": run_report,
            },
        )
    except Exception as exc:
        logger.exception("Narration background task failed")
        # Try to save whatever we have so far
        try:
            await _save_narrative_blocks(world_id, narrative_blocks)
        except Exception:
            pass
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))


async def _run_partial_narration_background(
    task_id: str, world_id: str, config: dict, timeline: dict,
    steps: list[str], existing_blocks: dict,
):
    """Background coroutine for partial narration with intermediate saves."""
    narrative_blocks = dict(existing_blocks or {})
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Narration partielle en cours…")

        narrative_blocks = await run_partial_narration(config, timeline, steps, existing_blocks)

        await update_task(task_id, progress=90, message="Sauvegarde…")

        if not await _save_narrative_blocks(world_id, narrative_blocks, set_narrated=True):
            await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
            return

        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Narration partielle terminée",
            result={"world_id": world_id, "steps_executed": steps},
        )
    except Exception as exc:
        logger.exception("Partial narration background task failed")
        try:
            await _save_narrative_blocks(world_id, narrative_blocks)
        except Exception:
            pass
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
