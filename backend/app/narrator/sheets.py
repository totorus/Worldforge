from app.narrator.json_utils import extract_json, unwrap_llm_json
"""Faction and region sheets — generates rich narrative descriptions."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.sheets")


def _normalize_string_list(items: list) -> list[str]:
    """Convert a list that may contain dicts to a list of strings."""
    result = []
    for item in items:
        if isinstance(item, dict):
            # Try common name fields, then stringify
            name = item.get("name", item.get("title", item.get("description", "")))
            if isinstance(name, str) and name:
                result.append(name)
            else:
                result.append(str(item))
        elif isinstance(item, str):
            result.append(item)
        else:
            result.append(str(item))
    return result


async def generate_faction_sheet(faction_config: dict, faction_history: list) -> dict:
    """Generate a rich narrative sheet for a faction.

    Args:
        faction_config: Faction definition from world config.
        faction_history: List of events involving this faction (from timeline).

    Returns:
        Dict with keys: id, name, description, culture, governance_description,
        strengths, weaknesses, notable_moments, current_state
    """
    faction_name = faction_config.get("name", "Faction inconnue")
    faction_id = faction_config.get("id", "unknown")
    genre = faction_config.get("_genre", "fantasy")

    # Build history summary
    history_lines = []
    for evt in faction_history[:30]:  # Cap to avoid token overflow
        year = evt.get("year", "?")
        event_id = evt.get("event_id", "")
        outcome = evt.get("outcome", {})
        history_lines.append(f"An {year} — {event_id}: {json.dumps(outcome, ensure_ascii=False)}")

    history_text = "\n".join(history_lines) if history_lines else "Aucun événement notable."

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un chroniqueur et conteur spécialisé dans la création de mondes fictifs. "
                "Tu écris toujours en français avec un style littéraire riche et évocateur. "
                f"Le monde est de genre « {genre} ». "
                "Tu dois créer une fiche narrative complète pour la faction décrite. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Crée une fiche narrative pour la faction « {faction_name} ».\n\n"
                f"Configuration :\n{json.dumps(faction_config, ensure_ascii=False, indent=2)}\n\n"
                f"Historique des événements :\n{history_text}\n\n"
                "Génère un JSON avec les champs suivants :\n"
                "- id : identifiant de la faction\n"
                "- name : nom de la faction\n"
                "- description : description narrative (3-5 phrases, style littéraire)\n"
                "- culture : description de la culture, coutumes et traditions (2-3 phrases)\n"
                "- governance_description : description du système de gouvernance (1-2 phrases)\n"
                "- strengths : liste de 2-3 forces\n"
                "- weaknesses : liste de 2-3 faiblesses\n"
                "- notable_moments : liste de 3-5 moments marquants de leur histoire\n"
                "- current_state : description de l'état actuel de la faction (1-2 phrases)\n"
            ),
        },
    ]

    logger.info("Generating faction sheet for '%s'", faction_name)
    response = await llm_router.complete(
        task="faction_sheet", messages=messages, temperature=0.8, max_tokens=3072
    )

    try:
        sheet = extract_json(response)
        sheet = unwrap_llm_json(sheet, expect_dict=True)
        # Extra fallback: if still a list, take first dict
        if isinstance(sheet, list):
            dicts = [x for x in sheet if isinstance(x, dict)]
            sheet = dicts[0] if dicts else sheet
        if not isinstance(sheet, dict):
            raise ValueError("Expected a JSON object")
        sheet["id"] = faction_id
        sheet["name"] = faction_name
        # Normalize list fields that LLM sometimes returns as dicts
        for field in ("strengths", "weaknesses", "notable_moments"):
            if isinstance(sheet.get(field), list):
                sheet[field] = _normalize_string_list(sheet[field])
        return sheet
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse faction sheet JSON for '%s': %s", faction_name, e)
        return {
            "id": faction_id,
            "name": faction_name,
            "description": f"La faction {faction_name} est un acteur majeur de ce monde.",
            "culture": "",
            "governance_description": "",
            "strengths": [],
            "weaknesses": [],
            "notable_moments": [],
            "current_state": "",
        }


async def generate_region_sheet(region_config: dict, region_history: list) -> dict:
    """Generate a rich narrative sheet for a region.

    Args:
        region_config: Region definition from world config.
        region_history: List of events involving this region (from timeline).

    Returns:
        Dict with keys: id, name, description, landscape, resources_description,
        strategic_importance, notable_events, atmosphere
    """
    region_name = region_config.get("name", "Région inconnue")
    region_id = region_config.get("id", "unknown")
    genre = region_config.get("_genre", "fantasy")

    history_lines = []
    for evt in region_history[:20]:
        year = evt.get("year", "?")
        event_id = evt.get("event_id", "")
        history_lines.append(f"An {year} — {event_id}")

    history_text = "\n".join(history_lines) if history_lines else "Aucun événement notable dans cette région."

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un géographe et conteur spécialisé dans la création de mondes fictifs. "
                "Tu écris toujours en français avec un style littéraire riche et évocateur. "
                f"Le monde est de genre « {genre} ». "
                "Tu dois créer une fiche narrative complète pour la région décrite. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Crée une fiche narrative pour la région « {region_name} ».\n\n"
                f"Configuration :\n{json.dumps(region_config, ensure_ascii=False, indent=2)}\n\n"
                f"Événements historiques dans cette région :\n{history_text}\n\n"
                "Génère un JSON avec les champs suivants :\n"
                "- id : identifiant de la région\n"
                "- name : nom de la région\n"
                "- description : description narrative du lieu (3-5 phrases, style littéraire)\n"
                "- landscape : description détaillée du paysage et de la géographie (2-3 phrases)\n"
                "- resources_description : description narrative des ressources (1-2 phrases)\n"
                "- strategic_importance : importance stratégique de la région (1-2 phrases)\n"
                "- notable_events : liste de 2-4 événements marquants survenus ici\n"
                "- atmosphere : ambiance et atmosphère du lieu (1-2 phrases)\n"
            ),
        },
    ]

    logger.info("Generating region sheet for '%s'", region_name)
    response = await llm_router.complete(
        task="region_sheet", messages=messages, temperature=0.8, max_tokens=3072
    )

    try:
        sheet = extract_json(response)
        sheet = unwrap_llm_json(sheet, expect_dict=True)
        if isinstance(sheet, list):
            dicts = [x for x in sheet if isinstance(x, dict)]
            sheet = dicts[0] if dicts else sheet
        if not isinstance(sheet, dict):
            raise ValueError("Expected a JSON object")
        sheet["id"] = region_id
        sheet["name"] = region_name
        # Normalize list fields that LLM sometimes returns as dicts
        for field in ("notable_events",):
            if isinstance(sheet.get(field), list):
                sheet[field] = _normalize_string_list(sheet[field])
        return sheet
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse region sheet JSON for '%s': %s", region_name, e)
        return {
            "id": region_id,
            "name": region_name,
            "description": f"La région {region_name} est un territoire notable de ce monde.",
            "landscape": "",
            "resources_description": "",
            "strategic_importance": "",
            "notable_events": [],
            "atmosphere": "",
        }
