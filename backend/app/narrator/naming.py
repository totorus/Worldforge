from app.narrator.json_utils import extract_json, unwrap_llm_json
"""Naming module — generates proper names for characters using LLM."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.naming")


async def generate_names(config: dict, timeline: dict) -> dict[str, str]:
    """Generate proper names for all character placeholders in the timeline.

    Returns:
        Dict mapping placeholder names to generated proper names.
    """
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")
    factions = {f["id"]: f for f in config.get("factions", [])}

    # Collect all unique character placeholders with their faction context
    placeholders: dict[str, dict] = {}
    for tick in timeline.get("ticks", []):
        for ce in tick.get("character_events", []):
            placeholder = ce.get("name_placeholder", "")
            if placeholder and placeholder not in placeholders:
                fac_id = ce.get("faction_id", "")
                fac = factions.get(fac_id, {})
                placeholders[placeholder] = {
                    "role": ce.get("role", "unknown"),
                    "faction_name": fac.get("name", fac_id),
                    "faction_traits": fac.get("cultural_traits", []),
                    "governance": fac.get("governance", "unknown"),
                }

    if not placeholders:
        return {}

    # Build naming request
    naming_list = []
    for placeholder, ctx in placeholders.items():
        naming_list.append({
            "placeholder": placeholder,
            "role": ctx["role"],
            "faction": ctx["faction_name"],
            "traits": ctx["faction_traits"],
        })

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un créateur de noms pour un monde fictif. "
                "Tu réponds toujours en français. "
                f"Le monde est de genre « {genre} » et s'appelle « {world_name} ». "
                "Les noms doivent être cohérents avec la culture de chaque faction. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                "Génère des noms propres pour les personnages suivants. "
                "Chaque nom doit refléter la culture de sa faction et son rôle.\n\n"
                f"{json.dumps(naming_list, ensure_ascii=False, indent=2)}\n\n"
                "Réponds avec un JSON de la forme : "
                '{{"placeholder_1": "Nom Propre 1", "placeholder_2": "Nom Propre 2", ...}}'
            ),
        },
    ]

    logger.info("Generating names for %d character placeholders", len(placeholders))
    response = await llm_router.complete(task="naming", messages=messages, temperature=0.8, max_tokens=4096)

    try:
        names = extract_json(response)
        names = unwrap_llm_json(names, expect_dict=True)
        if not isinstance(names, dict):
            raise ValueError("Expected a JSON object")
        return names
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse names JSON: %s\nRaw response: %s", e, response[:500])
        # Fallback: use placeholders as-is
        return {p: p for p in placeholders}
