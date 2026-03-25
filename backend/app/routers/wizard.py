import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

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
    mode: str | None = None


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
        [system_msg, {"role": "user", "content": "Commence la conversation."}],
        temperature=0.7,
    )

    greeting = _strip_markers(greeting)

    # Persist greeting — must replace the list to trigger JSONB change detection
    session.messages = [*session.messages, {"role": "assistant", "content": greeting}]
    flag_modified(session, "messages")
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

    # Build new messages list (replace, don't mutate in-place)
    new_messages = [*session.messages, {"role": "user", "content": body.content}]

    # Get LLM response
    response = await kimi_client.chat_completion(new_messages, temperature=0.7)

    # Append assistant response
    new_messages.append({"role": "assistant", "content": response})
    session.messages = new_messages
    flag_modified(session, "messages")

    # Try to detect step progression and mode
    new_step, new_mode = _detect_step(response, session.current_step, session.mode)
    session.current_step = new_step
    if new_mode:
        session.mode = new_mode

    # Strip markers from the response stored in messages
    clean_response = _strip_markers(response)
    new_messages[-1] = {"role": "assistant", "content": clean_response}
    session.messages = new_messages

    await db.commit()

    return WizardResponse(
        session_id=str(session.id),
        message=clean_response,
        step=session.current_step,
        status="active",
        mode=session.mode,
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

    # Resolve generation status
    generation_status = None
    if session.generation_task_id:
        from app.services.task_manager import get_task
        task = get_task(session.generation_task_id)
        if task:
            generation_status = task.status.value
        else:
            # Task not in memory (server restart) — deduce from world state
            world = await db.get(World, session.world_id) if session.world_id else None
            if world and world.status == "configured" and world.config:
                generation_status = "completed"
            else:
                generation_status = "failed"

    return {
        "session_id": str(session.id),
        "world_id": str(session.world_id) if session.world_id else None,
        "messages": visible,
        "step": session.current_step,
        "status": session.status,
        "mode": session.mode,
        "generation_task_id": session.generation_task_id,
        "generation_status": generation_status,
    }


@router.post("/{session_id}/finalize", response_model=WizardResponse)
async def finalize(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user.id, db)

    # Ask LLM to produce the final JSON
    new_messages = [*session.messages, {
        "role": "user",
        "content": "Produis maintenant le JSON de configuration complet pour ce monde. "
                   "Mets-le dans un bloc ```json ... ```. Assure-toi qu'il est valide et complet.",
    }]

    response = await kimi_client.chat_completion(
        new_messages,
        temperature=0.3,
        max_tokens=16384,
    )

    # If JSON is truncated (has ```json but no closing ```), ask Kimi to continue
    if "```json" in response:
        after_json = response.split("```json", 1)[-1]
        # Count ``` occurrences after the opening — if none, it's truncated
        closing_count = after_json.count("```")
        if closing_count == 0:
            new_messages.append({"role": "assistant", "content": response})
            new_messages.append({"role": "user", "content": "Continue le JSON exactement où tu t'es arrêté, sans répéter ce qui précède. Termine avec ```."})
            continuation = await kimi_client.chat_completion(
                new_messages,
                temperature=0.3,
                max_tokens=16384,
            )
            response = response + continuation

    new_messages = [*session.messages, {
        "role": "user",
        "content": "Produis maintenant le JSON de configuration complet pour ce monde. "
                   "Mets-le dans un bloc ```json ... ```. Assure-toi qu'il est valide et complet.",
    }, {"role": "assistant", "content": response}]
    session.messages = new_messages
    flag_modified(session, "messages")
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

    # Auto-repair common LLM generation issues before validation
    config = _auto_repair_config(config)

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
    """Extract the last JSON block from assistant messages.

    Handles both complete (```json...```) and truncated blocks.
    """
    for msg in reversed(messages):
        if msg["role"] != "assistant":
            continue
        content = msg["content"]
        # Look for ```json ... ``` blocks (complete)
        matches = re.findall(r"```json\s*\n(.*?)\n```", content, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                pass
        # Fallback: try extracting from ```json to end (truncated block)
        idx = content.find("```json")
        if idx >= 0:
            raw = content[idx + 7:].strip()
            # Remove closing ``` if present
            close = raw.rfind("```")
            if close > 0:
                raw = raw[:close].strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                continue
    return None


def _safe_id(item) -> str | None:
    """Extract ID from an item that could be a string or a dict with 'id'/'target' key."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("id") or item.get("target")
    return None


def _safe_ids(items) -> set[str]:
    """Extract a set of IDs from a list of items (strings or dicts)."""
    if not isinstance(items, list):
        return set()
    return {_safe_id(item) for item in items} - {None}


def _auto_repair_config(config: dict) -> dict:
    """Fix common issues in LLM-generated configs so validation passes.

    Target format (JSON Schema):
    - connections: [{target: str, traversal_difficulty: float}, ...]
    - tech_tree: {nodes: [{id, name, prerequisites, ...}, ...]}
    - event_pool: flat list with is_black_swan boolean
    """

    # --- 0. Normalize top-level containers ---

    # tech_tree: ensure {nodes: [...]}
    tech_tree = config.get("tech_tree", {"nodes": []})
    if isinstance(tech_tree, list):
        # Flat list of tech dicts → wrap in {nodes: [...]}
        config["tech_tree"] = {"nodes": [t for t in tech_tree if isinstance(t, dict)]}
    elif isinstance(tech_tree, dict) and "nodes" not in tech_tree:
        config["tech_tree"] = {"nodes": []}
    elif not isinstance(tech_tree, dict):
        config["tech_tree"] = {"nodes": []}
    tech_nodes = config["tech_tree"]["nodes"]

    # event_pool: ensure flat list
    event_pool = config.get("event_pool", [])
    if isinstance(event_pool, dict):
        # {normal_events: [...], black_swans: [...]} → merge into flat list
        flat = []
        for evt in event_pool.get("normal_events", []):
            if isinstance(evt, dict):
                evt.setdefault("is_black_swan", False)
                flat.append(evt)
        for evt in event_pool.get("black_swans", []):
            if isinstance(evt, dict):
                evt["is_black_swan"] = True
                flat.append(evt)
        config["event_pool"] = flat
    elif not isinstance(event_pool, list):
        config["event_pool"] = []

    # geography
    geography = config.get("geography", {})
    if not isinstance(geography, dict):
        config["geography"] = {"regions": []}
        geography = config["geography"]
    regions = geography.get("regions", [])
    if not isinstance(regions, list):
        regions = []
        geography["regions"] = regions
    regions = [r for r in regions if isinstance(r, dict) and "id" in r]
    geography["regions"] = regions
    region_ids = {r["id"] for r in regions}

    # --- 1. Normalize connections to {target, traversal_difficulty} objects ---
    for region in regions:
        conns = region.get("connections", [])
        if not isinstance(conns, list):
            conns = []
        normalized = []
        for conn in conns:
            if isinstance(conn, str):
                # String ID → convert to object with default difficulty
                if conn in region_ids and conn != region["id"]:
                    normalized.append({"target": conn, "traversal_difficulty": 0.5})
            elif isinstance(conn, dict):
                target = conn.get("target") or conn.get("id")
                if target and target in region_ids and target != region["id"]:
                    normalized.append({
                        "target": target,
                        "traversal_difficulty": conn.get("traversal_difficulty", 0.5),
                    })
        region["connections"] = normalized

    # Ensure bidirectional connections
    conn_map = {}
    for region in regions:
        for conn in region["connections"]:
            conn_map.setdefault(region["id"], set()).add(conn["target"])
    for region in regions:
        for conn in region["connections"]:
            target = conn["target"]
            if region["id"] not in conn_map.get(target, set()):
                # Find the target region and add reverse connection
                for other in regions:
                    if other["id"] == target:
                        other["connections"].append({
                            "target": region["id"],
                            "traversal_difficulty": conn["traversal_difficulty"],
                        })
                        conn_map.setdefault(target, set()).add(region["id"])
                        break

    # --- 2. Ensure all referenced resources exist ---
    resource_ids = _safe_ids(config.get("resources", []))
    for region in regions:
        res = region.get("resources", [])
        if isinstance(res, list):
            region["resources"] = [r for r in res if (r if isinstance(r, str) else "") in resource_ids]
        else:
            region["resources"] = []

    # --- 3. Ensure all referenced techs in initial_state exist + auto-add prerequisites ---
    tech_ids = {t["id"] for t in tech_nodes if isinstance(t, dict) and "id" in t}
    tech_prereqs = {t["id"]: t.get("prerequisites", []) for t in tech_nodes if isinstance(t, dict) and "id" in t}
    initial_state = config.get("initial_state", {})
    if not isinstance(initial_state, dict):
        config["initial_state"] = {"faction_states": [], "initial_relations": []}
        initial_state = config["initial_state"]
    for fs in initial_state.get("faction_states", []):
        if isinstance(fs, dict):
            techs = fs.get("unlocked_techs", [])
            if isinstance(techs, list):
                fs["unlocked_techs"] = [t for t in techs if t in tech_ids]
            else:
                fs["unlocked_techs"] = []
            # Auto-add missing prerequisites
            added = True
            while added:
                added = False
                unlocked = set(fs["unlocked_techs"])
                for tid in list(unlocked):
                    for prereq in tech_prereqs.get(tid, []):
                        if prereq in tech_ids and prereq not in unlocked:
                            fs["unlocked_techs"].append(prereq)
                            added = True

    # --- 4. Ensure all referenced regions in faction_states exist ---
    for fs in initial_state.get("faction_states", []):
        if isinstance(fs, dict):
            sr = fs.get("starting_regions", [])
            if isinstance(sr, list):
                fs["starting_regions"] = [r for r in sr if r in region_ids]
            else:
                fs["starting_regions"] = []

    # --- 5. Ensure all faction_ids in initial_state exist ---
    faction_ids = _safe_ids(config.get("factions", []))
    initial_state["faction_states"] = [
        fs for fs in initial_state.get("faction_states", [])
        if isinstance(fs, dict) and fs.get("faction_id") in faction_ids
    ]

    # --- 6. Ensure relations reference existing factions ---
    initial_state["initial_relations"] = [
        r for r in initial_state.get("initial_relations", [])
        if isinstance(r, dict) and r.get("faction_a") in faction_ids and r.get("faction_b") in faction_ids
    ]

    # --- 7. Remove cascades from non-black-swan events & validate cascade refs ---
    all_event_ids = {e.get("id", "") for e in config["event_pool"] if isinstance(e, dict)}
    for evt in config["event_pool"]:
        if not isinstance(evt, dict):
            continue
        if not evt.get("is_black_swan"):
            evt.pop("cascade", None)
        else:
            cascades = evt.get("cascade", [])
            if isinstance(cascades, list):
                evt["cascade"] = [
                    c for c in cascades
                    if isinstance(c, dict) and c.get("event") in all_event_ids
                ]

    # --- 8. Clamp numeric faction attributes to 0-1 ---
    for faction in config.get("factions", []):
        if not isinstance(faction, dict):
            continue
        attrs = faction.get("attributes", {})
        if isinstance(attrs, dict):
            for key, val in attrs.items():
                if isinstance(val, (int, float)):
                    attrs[key] = max(0.0, min(1.0, float(val)))

    # --- 9. Ensure meta has required fields with defaults ---
    meta = config.setdefault("meta", {})
    if not isinstance(meta, dict):
        config["meta"] = {}
        meta = config["meta"]
    meta.setdefault("seed", 42)
    meta.setdefault("simulation_years", 500)
    meta.setdefault("tick_duration_years", 5)
    meta.setdefault("chaos_level", 0.3)
    meta.setdefault("trope_subversion", 0.5)
    if meta.get("tick_duration_years") not in (1, 5, 10):
        meta["tick_duration_years"] = 5

    return config


def _detect_step(response: str, current_step: int, current_mode: str | None = None) -> tuple[int, str | None]:
    """Detect wizard step and mode from LLM response.

    Returns (step, mode) where mode is None if not detected in this message.
    Looks for:
    - Mode markers: [MODE:guided] or [MODE:surprise]
    - Step markers: 'Étape N/11' (guided) or 'Étape N/4' (surprise)
    Only advances forward, never backwards.
    """
    detected_mode = None

    # Detect mode marker
    mode_match = re.search(r"\[MODE:(guided|surprise)\]", response, re.IGNORECASE)
    if mode_match:
        detected_mode = mode_match.group(1).lower()

    # Detect step — support both /11 and /4 denominators
    matches = re.findall(r"[ÉéEe]tape\s+(\d{1,2})(?:\s*/\s*(\d{1,2}))?", response, re.IGNORECASE)
    detected_step = current_step
    if matches:
        for step_str, denom_str in matches:
            step_val = int(step_str)
            denom = int(denom_str) if denom_str else (4 if (current_mode == "surprise" or detected_mode == "surprise") else 11)
            max_step = denom
            if 1 <= step_val <= max_step and step_val >= current_step:
                detected_step = step_val

    return detected_step, detected_mode


def _strip_markers(text: str) -> str:
    """Remove internal markers from LLM responses before displaying."""
    text = re.sub(r"\[MODE:\w+\]", "", text)
    return text.strip()
