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


@router.post("/{world_id}/regenerate")
async def regenerate_world(
    world_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Regenerate world config from existing wizard conversation."""
    from app.services.task_manager import create_task, get_task, TaskStatus
    import asyncio

    # Get world
    world = await _get_user_world(world_id, db, user)

    # Find wizard session for this world
    result = await db.execute(
        select(WizardSession).where(
            WizardSession.world_id == world.id,
            WizardSession.user_id == user.id,
        ).order_by(WizardSession.created_at.desc())
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune session wizard trouvée pour ce monde",
        )

    # Check no generation already running
    if session.generation_task_id:
        existing = get_task(session.generation_task_id)
        if existing and existing.status == TaskStatus.RUNNING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Une génération est déjà en cours",
            )

    task = create_task(type="wizard_regenerate", world_id=str(world.id), user_id=str(user.id))
    session.generation_task_id = task.id
    await db.commit()

    asyncio.create_task(
        _run_regeneration(task.id, str(session.id), str(world.id), str(user.id))
    )

    return {"task_id": task.id, "status": "accepted"}


async def _run_regeneration(task_id: str, session_id: str, world_id: str, user_id: str):
    """Background task: regenerate world config from existing wizard conversation."""
    from app.services.task_manager import update_task, TaskStatus
    from app.services import kimi_client
    from app.routers.wizard import _extract_json_from_messages, _auto_repair_config
    from app.database import async_session
    from sqlalchemy.orm.attributes import flag_modified

    try:
        await update_task(task_id, status=TaskStatus.RUNNING, progress=10, message="Régénération en cours...")

        async with async_session() as db:
            result = await db.execute(
                select(WizardSession).where(WizardSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                await update_task(task_id, status=TaskStatus.FAILED, error="Session introuvable")
                return

            # Use conversation history up to the finalize step
            # Remove any previous finalize/generation messages to get a clean conversation
            clean_messages = []
            for msg in session.messages:
                if msg.get("role") == "user" and msg.get("content", "").startswith("[Génération automatique]"):
                    break
                if msg.get("role") == "user" and "Produis maintenant le JSON" in msg.get("content", ""):
                    break
                clean_messages.append(msg)

            # Ask Kimi to generate JSON
            finalize_messages = [*clean_messages, {
                "role": "user",
                "content": "Produis maintenant le JSON de configuration complet pour ce monde. "
                           "Mets-le dans un bloc ```json ... ```. Assure-toi qu'il est valide et complet. "
                           "Sois très créatif et généreux dans les détails. "
                           "IMPORTANT : génère un monde DIFFÉRENT du précédent, avec de nouveaux noms, de nouvelles idées.",
            }]

            await update_task(task_id, progress=30, message="Kimi crée un nouveau monde...")
            response = await kimi_client.chat_completion(finalize_messages, temperature=0.5, max_tokens=16384)

            # Handle truncated JSON
            if "```json" in response:
                after_json = response.split("```json", 1)[-1]
                if after_json.count("```") == 0:
                    finalize_messages.append({"role": "assistant", "content": response})
                    finalize_messages.append({"role": "user", "content": "Continue le JSON exactement où tu t'es arrêté, sans répéter ce qui précède. Termine avec ```."})
                    continuation = await kimi_client.chat_completion(finalize_messages, temperature=0.5, max_tokens=16384)
                    response = response + continuation

            await update_task(task_id, progress=70, message="Validation...")

            # Extract, repair, validate
            temp_messages = [{"role": "assistant", "content": response}]
            config = _extract_json_from_messages(temp_messages)
            if config is None:
                raise ValueError("Aucun JSON valide trouvé")

            config = _auto_repair_config(config)
            errors = validate_world_config(config)
            if errors:
                error_msgs = [e.message for e in errors[:5]]
                raise ValueError(f"Validation échouée: {'; '.join(error_msgs)}")

            await update_task(task_id, progress=90, message="Sauvegarde...")

            # Update world — clear downstream data
            world = await db.get(World, world_id)
            if not world:
                raise ValueError("Monde introuvable")

            world.config = config
            world.name = config.get("meta", {}).get("world_name", world.name)
            world.status = "configured"
            world.simulation_years = config.get("meta", {}).get("simulation_years")
            world.total_factions = len(config.get("factions", []))
            world.timeline = None
            world.narrative_blocks = None
            world.bookstack_mapping = None

            await db.commit()

        await update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Monde régénéré",
                          result={"world_id": world_id, "world_name": config.get("meta", {}).get("world_name", "")})

    except Exception as exc:
        import logging
        logging.getLogger("worldforge.worlds").exception("Regeneration failed")
        await update_task(task_id, status=TaskStatus.FAILED, progress=0, error=str(exc))
