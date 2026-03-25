"""Export router — Bookstack wiki export endpoints."""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, async_session
from app.exporter.pipeline import export_to_bookstack, sync_to_bookstack
from app.models.user import User
from app.models.world import World
from app.services.auth import get_current_user
from app.services.task_manager import (
    TaskStatus,
    create_task,
    update_task,
)

logger = logging.getLogger("worldforge.export")

router = APIRouter()


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


def _check_bookstack_configured() -> None:
    """Raise 503 if Bookstack tokens are not set."""
    if not settings.bookstack_token_id or not settings.bookstack_token_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Export Bookstack non disponible — tokens API non configurés",
        )


def _check_world_exportable(world: World) -> None:
    """Raise 409 if the world is not in an exportable state."""
    if world.status not in ("narrated", "published"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Le monde doit être au statut 'narrated' ou 'published' pour l'export "
                f"(statut actuel : '{world.status}')"
            ),
        )
    if not world.config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune configuration disponible pour ce monde",
        )
    if not world.timeline:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune timeline disponible — lancez d'abord la simulation",
        )
    if not world.narrative_blocks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucun contenu narratif — lancez d'abord la narration",
        )


async def _export_background(
    task_id: str, world_id: str, config: dict, timeline: dict,
    narrative_blocks: dict, world_name: str,
):
    """Background coroutine for Bookstack export."""
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Connexion à Bookstack…")

        await update_task(task_id, progress=20, message="Export en cours…")
        mapping = await export_to_bookstack(
            config=config,
            timeline=timeline,
            narrative_blocks=narrative_blocks,
            world_name=world_name,
        )

        await update_task(task_id, progress=90, message="Mise à jour du monde…")

        async with async_session() as db:
            result = await db.execute(select(World).where(World.id == world_id))
            world = result.scalar_one_or_none()
            if not world:
                await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
                return

            world.bookstack_mapping = mapping
            world.status = "published"
            await db.commit()

        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Export Bookstack terminé",
            result={"world_id": world_id, "bookstack_mapping": mapping},
        )
    except Exception as exc:
        logger.exception("Export background task failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))


async def _sync_background(
    task_id: str, world_id: str, config: dict, timeline: dict,
    narrative_blocks: dict, world_name: str, existing_mapping: dict,
):
    """Background coroutine for Bookstack sync."""
    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Synchronisation en cours…")

        mapping = await sync_to_bookstack(
            config=config,
            timeline=timeline,
            narrative_blocks=narrative_blocks,
            world_name=world_name,
            existing_mapping=existing_mapping,
        )

        await update_task(task_id, progress=90, message="Mise à jour du monde…")

        async with async_session() as db:
            result = await db.execute(select(World).where(World.id == world_id))
            world = result.scalar_one_or_none()
            if not world:
                await update_task(task_id, status=TaskStatus.FAILED, error="Monde introuvable")
                return

            world.bookstack_mapping = mapping
            await db.commit()

        await update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Synchronisation Bookstack terminée",
            result={"world_id": world_id, "bookstack_mapping": mapping},
        )
    except Exception as exc:
        logger.exception("Sync background task failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))


@router.post("/{world_id}/bookstack")
async def export_world_to_bookstack(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run the full Bookstack export for a narrated world (background task).

    Creates (or reuses) the shared "WorldForge" shelf, then a single book
    for this world with 7 chapters (Atlas, Chroniques, Factions, Personnages,
    Technologies, Légendes, Annexes).  Injects cross-references between pages.
    Saves the mapping and updates the status to ``published``.
    """
    _check_bookstack_configured()
    world = await _get_user_world(world_id, db, user)
    _check_world_exportable(world)

    task = create_task(type="export", world_id=str(world.id), user_id=str(user.id))
    asyncio.create_task(
        _export_background(
            task.id, str(world.id), world.config, world.timeline,
            world.narrative_blocks, world.name,
        )
    )

    return {
        "task_id": task.id,
        "world_id": str(world.id),
        "status": "accepted",
        "message": "Export Bookstack lancé en arrière-plan",
    }


@router.get("/{world_id}/bookstack/status")
async def export_status(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the current Bookstack export status and mapping."""
    world = await _get_user_world(world_id, db, user)

    exported = world.bookstack_mapping is not None
    return {
        "world_id": str(world.id),
        "status": world.status,
        "exported": exported,
        "bookstack_mapping": world.bookstack_mapping,
    }


@router.post("/{world_id}/bookstack/sync")
async def sync_world_bookstack(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-sync / update existing Bookstack wiki pages (background task).

    Requires the world to have been exported at least once (mapping must exist).
    """
    _check_bookstack_configured()
    world = await _get_user_world(world_id, db, user)
    _check_world_exportable(world)

    if not world.bookstack_mapping:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucun export existant — utilisez POST /{world_id}/bookstack d'abord",
        )

    task = create_task(type="export_sync", world_id=str(world.id), user_id=str(user.id))
    asyncio.create_task(
        _sync_background(
            task.id, str(world.id), world.config, world.timeline,
            world.narrative_blocks, world.name, world.bookstack_mapping,
        )
    )

    return {
        "task_id": task.id,
        "world_id": str(world.id),
        "status": "accepted",
        "message": "Synchronisation Bookstack lancée en arrière-plan",
    }
