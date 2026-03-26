from app.narrator.json_utils import extract_json, unwrap_llm_json
"""Era splitting — identifies major turning points and splits the timeline into named eras."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.eras")


def _build_timeline_summary(config: dict, timeline: dict) -> str:
    """Build a concise textual summary of the timeline for the LLM."""
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")
    factions = {f["id"]: f["name"] for f in config.get("factions", [])}
    regions = {r["id"]: r["name"] for r in config.get("geography", {}).get("regions", [])}

    lines = [
        f"Monde : {world_name} (genre : {genre})",
        f"Factions : {', '.join(factions.values())}",
        f"Régions : {', '.join(regions.values())}",
        "",
        "Chronologie des événements :",
    ]

    for tick in timeline.get("ticks", []):
        year = tick.get("year", "?")
        events = tick.get("events", [])
        tech_unlocks = tick.get("tech_unlocks", [])
        char_events = tick.get("character_events", [])

        if not events and not tech_unlocks and not char_events:
            continue

        for evt in events:
            evt_id = evt.get("event_id", "unknown")
            involved = [factions.get(f, f) for f in evt.get("involved_factions", [])]
            in_regions = [regions.get(r, r) for r in evt.get("involved_regions", [])]
            outcome = evt.get("outcome", {})
            line = f"  An {year} — {evt_id} impliquant {', '.join(involved)}"
            if in_regions:
                line += f" dans {', '.join(in_regions)}"
            if outcome:
                line += f" (résultat: {json.dumps(outcome, ensure_ascii=False)})"
            lines.append(line)

        for tech in tech_unlocks:
            fac_name = factions.get(tech.get("faction_id", ""), tech.get("faction_id", ""))
            lines.append(f"  An {year} — {fac_name} débloque la technologie {tech.get('tech_id', '?')}")

        for ce in char_events:
            fac_name = factions.get(ce.get("faction_id", ""), ce.get("faction_id", ""))
            action = "apparition" if ce.get("type") == "spawn" else "retrait"
            lines.append(f"  An {year} — {action} de {ce.get('name_placeholder', '?')} ({ce.get('role', '?')}) chez {fac_name}")

    return "\n".join(lines)


async def split_into_eras(config: dict, timeline: dict) -> list[dict]:
    """Split the timeline into narrative eras using LLM analysis.

    Returns:
        List of dicts with keys: name, start_year, end_year, description, key_events
    """
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")
    summary = _build_timeline_summary(config, timeline)

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un historien spécialisé dans la création de mondes fictifs. "
                "Tu réponds toujours en français. "
                f"Le monde est de genre « {genre} ». "
                "Tu dois analyser la chronologie fournie et identifier les grandes ères historiques, "
                "leurs points de rupture et les événements charnières. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Voici la chronologie complète du monde « {world_name} ».\n\n"
                f"{summary}\n\n"
                "Découpe cette chronologie en 3 à 6 ères narratives. "
                "Pour chaque ère, fournis :\n"
                "- name : nom évocateur de l'ère (en français)\n"
                "- start_year : année de début\n"
                "- end_year : année de fin\n"
                "- description : description narrative de l'ère (2-3 phrases)\n"
                "- key_events : liste des événements marquants (3-5 par ère)\n\n"
                "Réponds avec un JSON de la forme : [{\"name\": ..., \"start_year\": ..., "
                "\"end_year\": ..., \"description\": ..., \"key_events\": [...]}, ...]"
            ),
        },
    ]

    logger.info("Splitting timeline into eras for world '%s'", world_name)
    response = await llm_router.complete(task="era_splitting", messages=messages, temperature=0.6, max_tokens=4096)

    try:
        eras = extract_json(response)
        eras = unwrap_llm_json(eras, expect_list=True)
        if not isinstance(eras, list):
            raise ValueError("Expected a JSON list")
        # Validate structure
        for era in eras:
            era.setdefault("name", "Ère sans nom")
            era.setdefault("start_year", 0)
            era.setdefault("end_year", 0)
            era.setdefault("description", "")
            era.setdefault("key_events", [])
        return eras
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse eras JSON: %s\nRaw response: %s", e, response[:500])
        # Fallback: single era covering the whole timeline
        ticks = timeline.get("ticks", [])
        max_year = ticks[-1]["year"] if ticks else config.get("meta", {}).get("simulation_years", 500)
        return [
            {
                "name": f"Histoire de {world_name}",
                "start_year": 1,
                "end_year": max_year,
                "description": f"L'intégralité de l'histoire connue de {world_name}.",
                "key_events": [],
            }
        ]
