from app.narrator.json_utils import extract_json
"""Character biographies — generates rich biographies for notable characters."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.characters")


def _extract_characters(timeline: dict, config: dict, names: dict[str, str]) -> list[dict]:
    """Extract character data from the timeline with their context."""
    factions = {f["id"]: f for f in config.get("factions", [])}
    characters: dict[str, dict] = {}

    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)
        for ce in tick.get("character_events", []):
            placeholder = ce.get("name_placeholder", "")
            if not placeholder:
                continue

            if ce.get("type") == "spawn":
                characters[placeholder] = {
                    "placeholder": placeholder,
                    "name": names.get(placeholder, placeholder),
                    "role": ce.get("role", "unknown"),
                    "faction_id": ce.get("faction_id", ""),
                    "faction_name": factions.get(ce.get("faction_id", ""), {}).get("name", ""),
                    "spawn_year": year,
                    "end_year": None,
                    "events_involved": [],
                }
            elif ce.get("type") == "retire" and placeholder in characters:
                characters[placeholder]["end_year"] = year

    # Attach events the character was active during
    for tick in timeline.get("ticks", []):
        year = tick.get("year", 0)
        for evt in tick.get("events", []):
            for char_data in characters.values():
                if char_data["spawn_year"] <= year and (
                    char_data["end_year"] is None or year <= char_data["end_year"]
                ):
                    if char_data["faction_id"] in evt.get("involved_factions", []):
                        char_data["events_involved"].append({
                            "year": year,
                            "event_id": evt.get("event_id"),
                        })

    return list(characters.values())


async def generate_biographies(
    characters: list, config: dict, names: dict[str, str] | None = None
) -> list[dict]:
    """Generate rich biographies for notable characters.

    Args:
        characters: List of character dicts (from timeline extraction or direct).
        config: World configuration.
        names: Optional mapping of placeholders to proper names.

    Returns:
        List of biography dicts with keys: name, role, faction, birth_year,
        death_year, biography, personality, legacy
    """
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")
    names = names or {}

    if not characters:
        return []

    # Select most notable characters (up to 15)
    # Prioritize by number of events involved and impact
    scored = []
    for char in characters:
        event_count = len(char.get("events_involved", []))
        scored.append((event_count, char))
    scored.sort(key=lambda x: x[0], reverse=True)
    notable = [c for _, c in scored[:15]]

    # Build character list for the LLM
    char_descriptions = []
    for char in notable:
        char_descriptions.append({
            "name": char.get("name", char.get("placeholder", "Inconnu")),
            "role": char.get("role", "unknown"),
            "faction": char.get("faction_name", ""),
            "birth_year": char.get("spawn_year"),
            "death_year": char.get("end_year"),
            "events_involved": char.get("events_involved", [])[:5],  # Cap events
        })

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un biographe et conteur spécialisé dans la création de mondes fictifs. "
                "Tu écris toujours en français avec un style littéraire riche et évocateur. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Tu dois créer des biographies captivantes pour les personnages décrits. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                "Crée des biographies pour les personnages suivants :\n\n"
                f"{json.dumps(char_descriptions, ensure_ascii=False, indent=2)}\n\n"
                "Pour chaque personnage, génère :\n"
                "- name : nom du personnage\n"
                "- role : rôle (dirigeant, héros, érudit, traître, prophète...)\n"
                "- faction : faction d'appartenance\n"
                "- birth_year : année de naissance\n"
                "- death_year : année de mort (null si toujours en vie)\n"
                "- biography : biographie narrative (4-6 phrases, style littéraire)\n"
                "- personality : traits de personnalité (2-3 phrases)\n"
                "- legacy : héritage et impact sur le monde (1-2 phrases)\n\n"
                "Réponds avec une liste JSON."
            ),
        },
    ]

    logger.info("Generating biographies for %d characters", len(notable))
    response = await llm_router.complete(
        task="character_biography", messages=messages, temperature=0.85, max_tokens=4096
    )

    try:
        bios = extract_json(response)
        if not isinstance(bios, list):
            raise ValueError("Expected a JSON list")
        return bios
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse biographies JSON: %s", e)
        return [
            {
                "name": c.get("name", "Inconnu"),
                "role": c.get("role", ""),
                "faction": c.get("faction", ""),
                "birth_year": c.get("birth_year"),
                "death_year": c.get("death_year"),
                "biography": "",
                "personality": "",
                "legacy": "",
            }
            for c in char_descriptions
        ]
