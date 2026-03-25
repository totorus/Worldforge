from app.narrator.json_utils import extract_json
"""Coherence check — validates narrative content for internal consistency."""

import json
import logging

from app.services import llm_router

logger = logging.getLogger("worldforge.narrator.coherence")


def _to_str(value, max_len: int = 150) -> str:
    """Safely convert a value to a truncated string."""
    if isinstance(value, str):
        return value[:max_len]
    if isinstance(value, list):
        return str(value)[:max_len]
    if value is None:
        return ""
    return str(value)[:max_len]


async def check_coherence(narrative_blocks: dict, config: dict) -> dict:
    """Send all narrative content to LLM for coherence validation.

    Args:
        narrative_blocks: Complete narrative_blocks dict.
        config: World configuration.

    Returns:
        Dict with keys: score (float 0-1), issues (list), suggestions (list)
    """
    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    # Build a condensed summary of all narrative content
    summary_parts = []

    # Eras
    eras = narrative_blocks.get("eras", [])
    if eras:
        summary_parts.append("ÈRES :")
        for era in eras:
            summary_parts.append(f"  - {era.get('name', '?')} ({era.get('start_year', '?')}-{era.get('end_year', '?')}): {_to_str(era.get('description', ''))}")

    # Factions
    factions = narrative_blocks.get("factions", [])
    if factions:
        summary_parts.append("\nFACTIONS :")
        for fac in factions:
            summary_parts.append(f"  - {fac.get('name', '?')}: {_to_str(fac.get('description', ''))}")

    # Regions
    regions = narrative_blocks.get("regions", [])
    if regions:
        summary_parts.append("\nRÉGIONS :")
        for reg in regions:
            summary_parts.append(f"  - {reg.get('name', '?')}: {_to_str(reg.get('description', ''))}")

    # Key events
    events = narrative_blocks.get("events", [])
    if events:
        summary_parts.append("\nÉVÉNEMENTS CLÉS :")
        for evt in events[:20]:
            summary_parts.append(f"  - An {evt.get('year', '?')} — {evt.get('title', '?')}: {_to_str(evt.get('narrative', ''), 100)}")

    # Characters
    characters = narrative_blocks.get("characters", [])
    if characters:
        summary_parts.append("\nPERSONNAGES :")
        for char in characters[:10]:
            summary_parts.append(f"  - {char.get('name', '?')} ({char.get('faction', '?')}, {char.get('role', '?')}): {_to_str(char.get('biography', ''), 100)}")

    # Legends
    legends = narrative_blocks.get("legends", [])
    if legends:
        summary_parts.append("\nLÉGENDES :")
        for leg in legends:
            summary_parts.append(f"  - {leg.get('title', '?')}: {_to_str(leg.get('narrative', ''), 100)}")

    content_summary = "\n".join(summary_parts)

    # Also include config context
    faction_names = [f["name"] for f in config.get("factions", [])]
    region_names = [r["name"] for r in config.get("geography", {}).get("regions", [])]

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un relecteur et éditeur spécialisé dans la cohérence narrative de mondes fictifs. "
                "Tu réponds toujours en français. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Tu dois analyser le contenu narratif pour détecter les incohérences, "
                "les contradictions, les anachronismes et les problèmes de continuité. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Analyse la cohérence narrative du monde « {world_name} ».\n\n"
                f"Factions définies : {', '.join(faction_names)}\n"
                f"Régions définies : {', '.join(region_names)}\n\n"
                f"Contenu narratif :\n{content_summary}\n\n"
                "Évalue la cohérence globale et identifie les problèmes.\n"
                "Réponds avec un JSON contenant :\n"
                "- score : note de cohérence de 0.0 (incohérent) à 1.0 (parfait)\n"
                "- issues : liste d'incohérences détectées (chaque item est une string descriptive)\n"
                "- suggestions : liste de suggestions d'amélioration (chaque item est une string)\n"
            ),
        },
    ]

    logger.info("Running coherence check for world '%s'", world_name)
    response = await llm_router.complete(
        task="coherence_check", messages=messages, temperature=0.3, max_tokens=3072
    )

    try:
        result = extract_json(response)
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object")
        # Normalize score
        score = result.get("score", 0.5)
        if isinstance(score, (int, float)):
            score = max(0.0, min(1.0, float(score)))
        else:
            score = 0.5
        return {
            "score": score,
            "issues": result.get("issues", []),
            "suggestions": result.get("suggestions", []),
        }
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse coherence check JSON: %s", e)
        return {
            "score": 0.5,
            "issues": ["Impossible d'effectuer la vérification de cohérence automatique."],
            "suggestions": ["Relire manuellement le contenu narratif."],
        }
