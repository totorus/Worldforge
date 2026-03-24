"""Legends and myths — creates legends based on the world's history."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.legends")


async def generate_legends(config: dict, eras: list, narrative_blocks: dict) -> list[dict]:
    """Create 2-3 legends/myths based on the world's history.

    Args:
        config: World configuration.
        eras: List of era dicts from era splitting.
        narrative_blocks: Partial narrative_blocks built so far (factions, regions, events, characters).

    Returns:
        List of legend dicts with keys: title, era_origin, type, narrative,
        moral, related_factions, related_characters
    """
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    # Build context summary from existing narrative blocks
    faction_names = [f.get("name", "") for f in narrative_blocks.get("factions", [])]
    character_names = [c.get("name", "") for c in narrative_blocks.get("characters", [])[:10]]
    era_names = [e.get("name", "") for e in eras]

    # Extract the most dramatic events
    dramatic_events = []
    for evt in narrative_blocks.get("events", [])[:15]:
        dramatic_events.append({
            "title": evt.get("title", ""),
            "era": evt.get("era", ""),
            "narrative": evt.get("narrative", "")[:200],
        })

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un conteur mythique, créateur de légendes et de mythes fondateurs. "
                "Tu écris toujours en français avec un style épique et poétique. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Tu dois créer des légendes qui s'inspirent de l'histoire réelle du monde "
                "mais la transforment en récits mythifiés. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Voici le contexte du monde « {world_name} » :\n\n"
                f"Ères : {', '.join(era_names)}\n"
                f"Factions : {', '.join(faction_names)}\n"
                f"Personnages notables : {', '.join(character_names)}\n\n"
                f"Événements marquants :\n{json.dumps(dramatic_events, ensure_ascii=False, indent=2)}\n\n"
                "Crée 2 à 3 légendes ou mythes fondateurs pour ce monde. "
                "Les légendes doivent s'inspirer des événements réels mais les transformer "
                "en récits mythiques (exagérations, symbolisme, morale). "
                "Chaque légende peut être un mythe de création, une prophétie, "
                "un conte moral, ou un récit héroïque.\n\n"
                "Pour chaque légende, fournis :\n"
                "- title : titre de la légende (en français)\n"
                "- era_origin : ère dont elle s'inspire\n"
                "- type : type de légende (mythe_fondateur, prophétie, conte_moral, épopée_héroïque, récit_tragique)\n"
                "- narrative : le texte de la légende (8-15 phrases, style épique et poétique)\n"
                "- moral : la morale ou le message de la légende (1-2 phrases)\n"
                "- related_factions : factions liées\n"
                "- related_characters : personnages liés (ou inspirations)\n\n"
                "Réponds avec une liste JSON."
            ),
        },
    ]

    logger.info("Generating legends for world '%s'", world_name)
    response = await llm_router.complete(
        task="legend", messages=messages, temperature=0.9, max_tokens=4096
    )

    try:
        legends = json.loads(response.strip())
        if not isinstance(legends, list):
            raise ValueError("Expected a JSON list")
        return legends
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse legends JSON: %s", e)
        return [
            {
                "title": f"La légende de {world_name}",
                "era_origin": era_names[0] if era_names else "",
                "type": "mythe_fondateur",
                "narrative": f"Les origines mystérieuses de {world_name} se perdent dans la nuit des temps...",
                "moral": "",
                "related_factions": faction_names[:2],
                "related_characters": [],
            }
        ]
