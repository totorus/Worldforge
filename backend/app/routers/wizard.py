import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.session import WizardSession
from app.models.world import World
from app.models.user import User
from app.services.auth import get_current_user
from app.services import kimi_client
from app.services.wizard_prompt import get_system_prompt
from app.services.world_validator import validate_world_config

router = APIRouter()


class MessageRequest(BaseModel):
    content: str


class WizardResponse(BaseModel):
    session_id: str
    message: str
    step: int | None = None
    status: str = "active"


# --- Endpoints ---

@router.post("/start", response_model=WizardResponse)
async def start_wizard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Create a draft world
    world = World(user_id=current_user.id, name="Nouveau monde", status="draft")
    db.add(world)
    await db.flush()

    # Create wizard session
    system_msg = {"role": "system", "content": get_system_prompt()}
    session = WizardSession(
        user_id=current_user.id,
        world_id=world.id,
        messages=[system_msg],
        current_step=1,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Get initial greeting from LLM
    greeting = await kimi_client.chat_completion(
        [system_msg, {"role": "user", "content": "Commence le wizard. Demande-moi quel genre de monde je veux créer."}],
        temperature=0.7,
    )

    session.messages.append({"role": "assistant", "content": greeting})
    await db.commit()

    return WizardResponse(
        session_id=str(session.id),
        message=greeting,
        step=1,
    )


@router.post("/{session_id}/message", response_model=WizardResponse)
async def send_message(
    session_id: str,
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user.id, db)

    # Add user message
    session.messages.append({"role": "user", "content": body.content})

    # Get LLM response
    response = await kimi_client.chat_completion(session.messages, temperature=0.7)

    # Add assistant response
    session.messages.append({"role": "assistant", "content": response})

    # Try to detect step progression
    session.current_step = _detect_step(response, session.current_step)

    await db.commit()

    return WizardResponse(
        session_id=str(session.id),
        message=response,
        step=session.current_step,
    )


@router.get("/{session_id}/history")
async def get_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user.id, db)
    # Return messages without system prompt
    visible = [m for m in session.messages if m["role"] != "system"]
    return {
        "session_id": str(session.id),
        "messages": visible,
        "step": session.current_step,
        "status": session.status,
    }


@router.post("/{session_id}/finalize", response_model=WizardResponse)
async def finalize(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user.id, db)

    # Ask LLM to produce the final JSON
    session.messages.append({
        "role": "user",
        "content": "Produis maintenant le JSON de configuration complet pour ce monde. "
                   "Mets-le dans un bloc ```json ... ```. Assure-toi qu'il est valide et complet.",
    })

    response = await kimi_client.chat_completion(
        session.messages,
        temperature=0.3,  # Lower temperature for structured output
        max_tokens=8192,
    )

    session.messages.append({"role": "assistant", "content": response})
    await db.commit()

    return WizardResponse(
        session_id=str(session.id),
        message=response,
        step=11,
    )


@router.post("/{session_id}/validate")
async def validate(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user.id, db)

    # Extract JSON from the last assistant message
    config = _extract_json_from_messages(session.messages)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun JSON de configuration trouvé dans la conversation. Utilisez /finalize d'abord.",
        )

    # Validate
    errors = validate_world_config(config)
    if errors:
        return {
            "valid": False,
            "errors": [e.dict() for e in errors],
        }

    # Save config to world
    world = await db.get(World, session.world_id)
    if world:
        world.config = config
        world.name = config.get("meta", {}).get("world_name", world.name)
        world.status = "configured"
        world.simulation_years = config.get("meta", {}).get("simulation_years")
        world.total_factions = len(config.get("factions", []))

    session.status = "finalized"
    await db.commit()

    return {
        "valid": True,
        "world_id": str(session.world_id),
        "world_name": config.get("meta", {}).get("world_name", ""),
    }


# --- Helpers ---

async def _get_session(session_id: str, user_id, db: AsyncSession) -> WizardSession:
    result = await db.execute(
        select(WizardSession).where(
            WizardSession.id == session_id,
            WizardSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session wizard introuvable")
    return session


def _extract_json_from_messages(messages: list[dict]) -> dict | None:
    """Extract the last JSON block from assistant messages."""
    for msg in reversed(messages):
        if msg["role"] != "assistant":
            continue
        # Look for ```json ... ``` blocks
        matches = re.findall(r"```json\s*\n(.*?)\n```", msg["content"], re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                continue
    return None


def _detect_step(response: str, current_step: int) -> int:
    """Simple heuristic to detect wizard step from LLM response."""
    keywords = {
        2: ["chaos", "subversion", "curseur"],
        3: ["géographie", "région", "terrain"],
        4: ["faction", "gouvernance", "peuple"],
        5: ["ressource", "matière"],
        6: ["technologie", "pouvoir", "arbre tech"],
        7: ["événement", "black swan", "catastrophe"],
        8: ["personnage", "rôle", "héros"],
        9: ["état initial", "condition de départ", "population initiale"],
        10: ["durée", "simulation", "tick", "années"],
        11: ["résumé", "validation", "confirmation", "récapitulatif"],
    }

    response_lower = response.lower()
    for step, words in keywords.items():
        if step > current_step:
            if any(w in response_lower for w in words):
                return step

    return current_step
