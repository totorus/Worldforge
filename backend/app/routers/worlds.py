"""Worlds router — CRUD operations on worlds for the authenticated user."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.session import WizardSession
from app.models.world import World
from app.services.auth import get_current_user
from app.services.world_validator import validate_world_config

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


@router.get("/")
async def list_worlds(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Liste tous les mondes de l'utilisateur courant."""
    result = await db.execute(
        select(World).where(World.user_id == user.id).order_by(World.updated_at.desc())
    )
    worlds = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "name": w.name,
            "status": w.status,
            "simulation_years": w.simulation_years,
            "total_factions": w.total_factions,
            "total_events": w.total_events,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
        }
        for w in worlds
    ]


@router.get("/{world_id}")
async def get_world(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Détails complets d'un monde (config, timeline, narrative_blocks)."""
    world = await _get_user_world(world_id, db, user)
    return {
        "id": str(world.id),
        "name": world.name,
        "status": world.status,
        "config": world.config,
        "timeline": world.timeline,
        "narrative_blocks": world.narrative_blocks,
        "simulation_years": world.simulation_years,
        "total_factions": world.total_factions,
        "total_events": world.total_events,
        "created_at": world.created_at.isoformat() if world.created_at else None,
        "updated_at": world.updated_at.isoformat() if world.updated_at else None,
    }


@router.put("/{world_id}/config")
async def update_config(
    world_id: UUID,
    config: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Met à jour la configuration d'un monde après validation."""
    world = await _get_user_world(world_id, db, user)

    # Validate the config
    errors = validate_world_config(config)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Configuration invalide",
                "errors": [e.dict() for e in errors],
            },
        )

    world.config = config
    world.status = "configured"
    # Update faction count from config
    world.total_factions = len(config.get("factions", []))
    world.simulation_years = config.get("meta", {}).get("simulation_years")

    await db.commit()
    await db.refresh(world)

    return {
        "id": str(world.id),
        "name": world.name,
        "status": world.status,
        "config": world.config,
        "total_factions": world.total_factions,
        "simulation_years": world.simulation_years,
        "updated_at": world.updated_at.isoformat() if world.updated_at else None,
    }


@router.delete("/{world_id}")
async def delete_world(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supprime un monde et ses sessions wizard associées."""
    world = await _get_user_world(world_id, db, user)
    # Delete related wizard sessions first (FK constraint)
    sessions = await db.execute(
        select(WizardSession).where(WizardSession.world_id == world.id)
    )
    for session in sessions.scalars().all():
        await db.delete(session)
    await db.delete(world)
    await db.commit()
    return {"message": "Monde supprimé"}


@router.get("/{world_id}/timeline")
async def get_timeline(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne les données de timeline d'un monde."""
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


@router.get("/{world_id}/narrative")
async def get_narrative(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne les blocs narratifs d'un monde."""
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
